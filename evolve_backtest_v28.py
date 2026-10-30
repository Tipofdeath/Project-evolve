"""EVOLVE 2.8: research-only hourly intraday holding-period comparison.
Usage: python evolve_backtest_v28.py [market_snapshot.json]
No broker orders. Costs are assumptions; closes are not executable quotes.
"""
import json
import math
import statistics
import sys
from pathlib import Path

STRATEGIES = ('trend', 'momentum', 'breakout', 'mean_reversion')
HOLDS = (2, 4, 6)
COST = {'crypto': .0025, 'forex': .0002, 'gold': .0005}
# Adverse slippage per side: scenario assumptions, not observed fills.
SLIPPAGE = {'crypto': .0010, 'forex': .0001, 'gold': .0002}
THRESHOLDS = {
    'crypto': {'trend': .001, 'momentum': .015, 'regime': .004},
    'forex': {'trend': .00012, 'momentum': .0012, 'regime': .00045},
    'gold': {'trend': .0005, 'momentum': .005, 'regime': .0015},
}
WARMUP = 60
MIN_BARS = 300
MIN_COMPLETED_TRADES = 20
MAX_EXECUTION_DRAG_PCT_POINTS = 10.0
MIN_WIN_RATE_PCT = 30.0


def mean(xs):
    return sum(xs) / len(xs)


def market_regime(p, i, cfg):
    h = p[i-40:i]
    changes = [h[j] / h[j-1] - 1 for j in range(1, len(h))]
    vol = statistics.pstdev(changes[-19:])
    drift = abs(mean(h[-10:]) / mean(h) - 1)
    if vol > cfg['regime'] * 8:
        return 'high_volatility'
    if drift > max(cfg['regime'], vol * .75):
        return 'trending'
    return 'ranging'


def signal(strategy, p, i, cfg):
    h = p[:i]  # strictly prior closes; decision for bar i
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


def simulate(p, strategy, start, end, category, hold=None, cost_override=None):
    """Long/flat; decision based on previous close, fills approximated at current close.
    A fixed hold exits after `hold` bars, never re-enters on the same bar.
    End-of-window positions are liquidated at final available close.
    Execution cost combines fees and adverse assumed slippage per side.
    """
    cfg = THRESHOLDS[category]
    cost = (1 - (1 - COST[category]) * (1 - SLIPPAGE[category])) if cost_override is None else cost_override
    if not 0 <= cost < 1:
        raise ValueError('Invalid execution cost')
    cash, units, peak, max_dd, orders = 1., 0., 1., 0., 0
    entry_price = entry_bar = None
    trades, exposure, signals, blocked = [], 0, 0, 0
    for i in range(start, end):
        regime = market_regime(p, i, cfg)
        sig = signal(strategy, p, i, cfg)
        allowed = regime != 'high_volatility' and (
            regime == ('ranging' if strategy == 'mean_reversion' else 'trending'))
        if sig:
            signals += 1
            if not allowed:
                blocked += 1
        target = sig and allowed
        price = p[i]
        if units:
            exit_now = (i - entry_bar >= hold) if hold is not None else not target
            if exit_now:
                cash = units * price * (1 - cost)
                units = 0.
                orders += 1
                trades.append({'gross': (price / entry_price - 1) * 100,
                               'net': (price / entry_price * (1 - cost)**2 - 1) * 100,
                               'bars': i - entry_bar})
                entry_price = entry_bar = None
                # No same-bar re-entry after an exit.
        elif target and i < end - 1:
            units = cash * (1 - cost) / price
            cash = 0.
            orders += 1
            entry_price, entry_bar = price, i
        if units:
            exposure += 1
        equity = cash + units * price
        peak = max(peak, equity)
        max_dd = max(max_dd, (peak - equity) / peak)
    if units:
        price = p[end - 1]
        cash = units * price * (1 - cost)
        orders += 1
        trades.append({'gross': (price / entry_price - 1) * 100,
                       'net': (price / entry_price * (1 - cost)**2 - 1) * 100,
                       'bars': end - 1 - entry_bar})
        max_dd = max(max_dd, (peak - cash) / peak)
    wins = sum(t['net'] > 0 for t in trades)
    return {
        'return_pct': round((cash - 1) * 100, 3),
        'max_drawdown_pct': round(max_dd * 100, 3),
        'orders': orders,
        'diagnostics': {
            'completed_trades': len(trades),
            'winning_trades': wins,
            'win_rate_pct': round(wins * 100 / len(trades), 2) if trades else None,
            'avg_holding_bars': round(mean([t['bars'] for t in trades]), 2) if trades else None,
            'avg_gross_trade_pct': round(mean([t['gross'] for t in trades]), 4) if trades else None,
            'avg_net_trade_pct': round(mean([t['net'] for t in trades]), 4) if trades else None,
            'exposure_pct': round(exposure * 100 / (end - start), 2),
            'signal_true': signals, 'regime_blocked': blocked,
        },
    }


def choose(training):
    """Conservative, in-sample eligibility only. Never use holdout to select."""
    reasons, eligible = {}, []
    for key, result in training.items():
        why = []
        d = result['diagnostics']
        if d['completed_trades'] < MIN_COMPLETED_TRADES:
            why.append('fewer_than_20_completed_trades')
        if result['return_pct'] <= 1:
            why.append('training_return_not_above_1pct')
        if result['max_drawdown_pct'] >= 8:
            why.append('drawdown_at_least_8pct')
        if d['execution_drag_pct_points'] > MAX_EXECUTION_DRAG_PCT_POINTS:
            why.append('execution_drag_above_10_percentage_points')
        if d['win_rate_pct'] is None or d['win_rate_pct'] < MIN_WIN_RATE_PCT:
            why.append('win_rate_below_30pct')
        reasons[key] = why
        if not why:
            eligible.append(key)
    # Ranking is heuristic, not an estimated future return.
    return (max(eligible, key=lambda k: (
                training[k]['return_pct'] - training[k]['max_drawdown_pct']
                - training[k]['diagnostics']['execution_drag_pct_points']))
            if eligible else None), reasons


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
    boundaries = [int(n * x) for x in (.55, .70, .85, 1.)]
    folds = []
    for fold_idx in range(3):
        train_end, test_end = boundaries[fold_idx], boundaries[fold_idx + 1]
        configurations = [(s, None) for s in STRATEGIES] + [(s, h) for s in STRATEGIES for h in HOLDS]
        training = {}
        for strategy, hold in configurations:
            key = f'{strategy}__' + ('signal_exit' if hold is None else f'hold_{hold}h')
            net = simulate(p, strategy, WARMUP, train_end, category, hold)
            gross = simulate(p, strategy, WARMUP, train_end, category, hold, cost_override=0.)
            net['diagnostics']['zero_cost_return_pct'] = gross['return_pct']
            net['diagnostics']['execution_drag_pct_points'] = round(gross['return_pct'] - net['return_pct'], 3)
            training[key] = net
        selected, rejection = choose(training)
        holdout = None
        if selected:
            strategy, variant = selected.split('__', 1)
            hold = None if variant == 'signal_exit' else int(variant.split('_')[1][:-1])
            holdout = simulate(p, strategy, train_end, test_end, category, hold)
            gross = simulate(p, strategy, train_end, test_end, category, hold, cost_override=0.)
            holdout['diagnostics']['zero_cost_return_pct'] = gross['return_pct']
            holdout['diagnostics']['execution_drag_pct_points'] = round(gross['return_pct'] - holdout['return_pct'], 3)
        folds.append({
            'training_bars': train_end - WARMUP,
            'holdout_bars': test_end - train_end,
            'selected_strategy': selected or 'NO_TRADE',
            'rejection_reasons': rejection,
            'training_results': training,
            'holdout': holdout,
            'holdout_buy_hold_pct': round((p[test_end - 1] / p[train_end] - 1) * 100, 3),
        })
    return dict(result, status='EXPERIMENTAL_ONLY', folds=folds,
                assumed_cost_per_side_pct=COST[category] * 100,
                assumed_slippage_per_side_pct=SLIPPAGE[category] * 100,
                warning='Research only. Hourly close-only approximation; fixed adverse slippage allowance but no observed spread, intrabar stops, liquidity constraints or financing. Holding periods are bar counts, not guaranteed wall-clock hours. Training windows overlap; thresholds were adjusted after inspecting earlier results and require fresh unseen-data validation. No live-performance claims.')


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('market_snapshot.json')
    data = json.loads(path.read_text(encoding='utf-8'))
    results = [evaluate(m) for m in data['markets']]
    output = {'version': '2.8', 'mode': 'research-only; no orders',
              'source_generated_at': data.get('generated_at'),
              'tested_holding_bars': list(HOLDS), 'selection_filters': {'min_completed_trades': MIN_COMPLETED_TRADES, 'max_drawdown_pct_exclusive': 8, 'min_training_return_pct_exclusive': 1, 'max_execution_drag_pct_points': MAX_EXECUTION_DRAG_PCT_POINTS, 'min_win_rate_pct': MIN_WIN_RATE_PCT}, 'results': results}
    Path('backtest_report_v28.json').write_text(json.dumps(output, indent=2), encoding='utf-8')
    for r in results:
        if r['status'] == 'EXPERIMENTAL_ONLY':
            print(f"{r['symbol']}: " + ', '.join(
                f"{f['selected_strategy']} ({f['holdout']['return_pct']:+.2f}% holdout)"
                if f['holdout'] else 'NO_TRADE' for f in r['folds']))
        else:
            print(f"{r['symbol']}: {r['status']}")
    print('Saved backtest_report_v28.json')


if __name__ == '__main__':
    main()
