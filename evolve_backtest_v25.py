"""Project EVOLVE 2.5 — cost and trade diagnostics, walk-forward research.
Run: python evolve_backtest_v25.py [market_snapshot.json]
Read-only; never sends orders. Costs are illustrative, not broker quotes.
"""
import json
import math
import statistics
import sys
from pathlib import Path

STRATEGIES = ('trend', 'momentum', 'breakout', 'mean_reversion')
COST = {'crypto': .0025, 'forex': .0002, 'gold': .0005}
# Relative thresholds reflect different volatility scales; not optimized for returns.
THRESHOLDS = {
    'crypto': {'trend': .001, 'momentum': .015, 'regime': .004},
    'forex': {'trend': .00012, 'momentum': .0012, 'regime': .00045},
    'gold': {'trend': .0005, 'momentum': .005, 'regime': .0015},
}
WARMUP = 60
MIN_BARS = 300


def mean(xs):
    return sum(xs) / len(xs)


def market_regime(p, i, cfg):
    h = p[i-40:i]
    changes = [h[j] / h[j-1] - 1 for j in range(1, len(h))]
    vol = statistics.pstdev(changes[-19:])
    drift = abs(mean(h[-10:]) / mean(h) - 1)
    if vol > cfg['regime'] * 8:
        return 'high_volatility'
    if drift > max(cfg['regime'], vol * 0.75):
        return 'trending'
    return 'ranging'


def signal(strategy, p, i, cfg):
    h = p[:i]
    if strategy == 'trend':
        return mean(h[-10:]) > mean(h[-30:]) * (1 + cfg['trend'])
    if strategy == 'momentum':
        return h[-1] > h[-13] * (1 + cfg['momentum']) and mean(h[-5:]) > mean(h[-20:])
    if strategy == 'breakout':
        return h[-1] > max(h[-21:-1])
    if strategy == 'mean_reversion':
        sd = statistics.pstdev(h[-20:])
        return sd > 0 and h[-1] < mean(h[-20:]) - 1.5 * sd
    return False


def simulate(p, strategy, start, end, category, adaptive=True, cost_override=None):
    """Long/flat close-only research simulation; signals use previous closes."""
    cfg = THRESHOLDS[category]
    cost = COST[category] if cost_override is None else cost_override
    cash, units, peak, dd, orders = 1., 0., 1., 0., 0
    entry_price, entry_bar = None, None
    completed = []
    exposed = 0
    diag = {'signal_true': 0, 'regime_blocked': 0, 'eligible_bars': 0, 'entries': 0}
    for i in range(start, end):
        r = market_regime(p, i, cfg)
        s = signal(strategy, p, i, cfg)
        allowed = r != 'high_volatility' and (not adaptive or (
            r == 'trending' if strategy != 'mean_reversion' else r == 'ranging'))
        if s:
            diag['signal_true'] += 1
            if not allowed:
                diag['regime_blocked'] += 1
        if allowed:
            diag['eligible_bars'] += 1
        target = s and allowed
        price = p[i]
        if target and units == 0:
            units = cash * (1 - cost) / price
            cash = 0.
            orders += 1
            diag['entries'] += 1
            entry_price, entry_bar = price, i
        elif not target and units > 0:
            cash = units * price * (1 - cost)
            units = 0.
            orders += 1
            completed.append({'gross_return_pct': (price / entry_price - 1) * 100,
                              'net_return_pct': (price / entry_price * (1 - cost)**2 - 1) * 100,
                              'holding_bars': i - entry_bar})
            entry_price, entry_bar = None, None
        if units:
            exposed += 1
        equity = cash + units * price
        peak = max(peak, equity)
        dd = max(dd, (peak - equity) / peak)
    if units:
        price = p[end - 1]
        cash = units * price * (1 - cost)
        orders += 1
        completed.append({'gross_return_pct': (price / entry_price - 1) * 100,
                          'net_return_pct': (price / entry_price * (1 - cost)**2 - 1) * 100,
                          'holding_bars': end - 1 - entry_bar})
        dd = max(dd, (peak - cash) / peak)
    wins = sum(t['net_return_pct'] > 0 for t in completed)
    return {'return_pct': round((cash - 1) * 100, 3),
            'max_drawdown_pct': round(dd * 100, 3), 'orders': orders,
            'diagnostics': dict(diag,
                completed_trades=len(completed),
                winning_trades=wins,
                losing_or_flat_trades=len(completed) - wins,
                win_rate_pct=round(100 * wins / len(completed), 2) if completed else None,
                avg_holding_bars=round(mean([t['holding_bars'] for t in completed]), 2) if completed else None,
                avg_gross_trade_pct=round(mean([t['gross_return_pct'] for t in completed]), 4) if completed else None,
                avg_net_trade_pct=round(mean([t['net_return_pct'] for t in completed]), 4) if completed else None,
                exposure_pct=round(100 * exposed / (end - start), 2))}

def choose(training):
    reasons = {}
    eligible = []
    for s, v in training.items():
        why = []
        if v['orders'] < 4:
            why.append('fewer_than_4_orders')
        if v['return_pct'] <= 1.0:
            why.append('training_return_not_above_1pct')
        if v['max_drawdown_pct'] >= 8.0:
            why.append('drawdown_at_least_8pct')
        reasons[s] = why
        if not why:
            eligible.append(s)
    selected = max(eligible, key=lambda s: training[s]['return_pct'] - training[s]['max_drawdown_pct']) if eligible else None
    return selected, reasons


def evaluate(m):
    result = {'symbol': m.get('symbol'), 'market': m.get('market')}
    category = result['market']
    if category not in THRESHOLDS:
        return dict(result, status='INVALID_CATEGORY')
    try:
        candles = m['candles']
        times = [str(c['time']) for c in candles]
        p = [float(c['close']) for c in candles]
        if not p or any(not math.isfinite(x) or x <= 0 for x in p):
            raise ValueError('nonpositive or nonfinite prices')
        if times != sorted(times) or len(set(times)) != len(times):
            raise ValueError('timestamps not strictly increasing')
    except (KeyError, ValueError, TypeError) as exc:
        return dict(result, status='INVALID_DATA', reason=str(exc))
    n = len(p)
    result['candles'] = n
    if n < MIN_BARS:
        return dict(result, status='INSUFFICIENT_HISTORY', required=MIN_BARS)
    # Three expanding training windows with consecutive nonoverlapping holdouts.
    # Every choice uses only bars before its own holdout. No holdout is used for tuning.
    boundaries = [int(n * x) for x in (.55, .70, .85, 1.)]
    folds = []
    for fold_idx in range(3):
        train_end, test_end = boundaries[fold_idx], boundaries[fold_idx + 1]
        training = {s: simulate(p, s, WARMUP, train_end, category) for s in STRATEGIES}
        for s in STRATEGIES:
            gross = simulate(p, s, WARMUP, train_end, category, cost_override=0.0)
            training[s]['diagnostics']['zero_fee_return_pct'] = gross['return_pct']
            training[s]['diagnostics']['fee_drag_pct_points'] = round(
                gross['return_pct'] - training[s]['return_pct'], 3)
        chosen, rejection = choose(training)
        holdout = simulate(p, chosen, train_end, test_end, category) if chosen else None
        if holdout:
            gross = simulate(p, chosen, train_end, test_end, category, cost_override=0.0)
            holdout['diagnostics']['zero_fee_return_pct'] = gross['return_pct']
            holdout['diagnostics']['fee_drag_pct_points'] = round(
                gross['return_pct'] - holdout['return_pct'], 3)
        folds.append({'training_bars': train_end - WARMUP, 'holdout_bars': test_end - train_end,
                      'selected_strategy': chosen or 'NO_TRADE',
                      'rejection_reasons': rejection, 'training_results': training,
                      'holdout': holdout,
                      'holdout_buy_hold_pct': round((p[test_end-1] / p[train_end] - 1)*100, 3)})
    return dict(result, status='EXPERIMENTAL_ONLY', folds=folds,
                assumed_cost_per_side_pct=COST[category] * 100,
                warning='Research only; close-only fills, assumed fees, no spread/slippage/financing. Fold results are not live forecasts.')


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('market_snapshot.json')
    data = json.loads(path.read_text(encoding='utf-8'))
    results = [evaluate(m) for m in data['markets']]
    output = {'version': '2.5', 'mode': 'research-only; no orders',
              'source_generated_at': data.get('generated_at'), 'results': results}
    Path('backtest_report_v25.json').write_text(json.dumps(output, indent=2), encoding='utf-8')
    for r in results:
        if r['status'] == 'EXPERIMENTAL_ONLY':
            summary = ', '.join(f"{f['selected_strategy']} ({f['holdout']['return_pct']:+.2f}% holdout)" if f['holdout'] else 'NO_TRADE' for f in r['folds'])
            print(f"{r['symbol']}: {summary}")
        else:
            print(f"{r['symbol']}: {r['status']}")
    print('Saved backtest_report_v25.json')


if __name__ == '__main__':
    main()
