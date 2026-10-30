"""EVOLVE 3.0: preregistered, research-only extended-hold experiments.

No orders. Candidate strategies are diagnostic experiments, NOT approved signals.
Each candidate is evaluated on fixed chronological holdouts without using those
holdouts to pick a winner. The original v2.8 safety filters remain unchanged.
"""
import json
import math
import sys
from pathlib import Path
from evolve_backtest_v28 import (
    COST, SLIPPAGE, THRESHOLDS, WARMUP, MIN_BARS, mean, market_regime,
    signal, simulate,
)

HOLDS = (12, 24, 48)
CONFIGS = (('trend', h) for h in HOLDS)
MAX_DRAWDOWN = 8.0
MAX_DRAG = 10.0
MIN_TRADES = 20
MIN_RETURN = 1.0
MIN_WIN_RATE = 30.0


def filtered_simulate(prices, start, end, category, hold, *, zero_cost=False):
    """Trend entry needs stronger confirmation and avoids high volatility.

    Previous closes only for decisions. Current close is an approximate fill.
    Exit after hold bars; no same-bar reentry; force close at window end.
    """
    cfg = THRESHOLDS[category]
    cost = 0.0 if zero_cost else 1 - (1 - COST[category]) * (1 - SLIPPAGE[category])
    cash, units, peak, drawdown = 1.0, 0.0, 1.0, 0.0
    entry = entry_bar = None
    trades, orders = [], 0
    for i in range(start, end):
        past = prices[:i]
        vol_changes = [past[j] / past[j - 1] - 1 for j in range(len(past) - 20, len(past))]
        volatility = math.sqrt(sum((v - mean(vol_changes)) ** 2 for v in vol_changes) / len(vol_changes))
        strong_trend = (mean(past[-10:]) > mean(past[-30:]) * (1 + cfg['trend'] * 2)
                        and past[-1] > mean(past[-10:]))
        allowed = market_regime(prices, i, cfg) == 'trending' and volatility <= cfg['regime'] * 4
        price = prices[i]
        if units:
            if i - entry_bar >= hold:
                cash = units * price * (1 - cost)
                trades.append((price / entry * (1 - cost) ** 2 - 1) * 100)
                units = 0.0
                orders += 1
                entry = entry_bar = None
        elif strong_trend and allowed and i < end - 1:
            units = cash * (1 - cost) / price
            cash = 0.0
            orders += 1
            entry, entry_bar = price, i
        equity = cash + units * price
        peak = max(peak, equity)
        drawdown = max(drawdown, (peak - equity) / peak)
    if units:
        cash = units * prices[end - 1] * (1 - cost)
        trades.append((prices[end - 1] / entry * (1 - cost) ** 2 - 1) * 100)
        orders += 1
        drawdown = max(drawdown, (peak - cash) / peak)
    return {'return_pct': round((cash - 1) * 100, 3),
            'max_drawdown_pct': round(drawdown * 100, 3),
            'orders': orders,
            'completed_trades': len(trades),
            'win_rate_pct': round(100 * sum(t > 0 for t in trades) / len(trades), 2) if trades else None}


def metrics(prices, start, end, category, strategy, hold, filtered):
    if filtered:
        net = filtered_simulate(prices, start, end, category, hold)
        gross = filtered_simulate(prices, start, end, category, hold, zero_cost=True)
    else:
        net = simulate(prices, strategy, start, end, category, hold)
        gross = simulate(prices, strategy, start, end, category, hold, cost_override=0)
        net = {**{k: net[k] for k in ('return_pct', 'max_drawdown_pct', 'orders')},
               'completed_trades': net['diagnostics']['completed_trades'],
               'win_rate_pct': net['diagnostics']['win_rate_pct']}
    net['execution_drag_pct_points'] = round(gross['return_pct'] - net['return_pct'], 3)
    net['zero_cost_return_pct'] = gross['return_pct']
    return net


def evaluate(m):
    symbol, category = m.get('symbol'), m.get('market')
    if category not in THRESHOLDS:
        return {'symbol': symbol, 'status': 'INVALID_CATEGORY'}
    try:
        candles = m['candles']
        times = [str(c['time']) for c in candles]
        prices = [float(c['close']) for c in candles]
        if (not prices or any(not math.isfinite(x) or x <= 0 for x in prices)
                or times != sorted(times) or len(set(times)) != len(times)):
            raise ValueError('invalid prices or timestamps')
    except (KeyError, ValueError, TypeError) as exc:
        return {'symbol': symbol, 'status': 'INVALID_DATA', 'reason': str(exc)}
    if len(prices) < MIN_BARS:
        return {'symbol': symbol, 'status': 'INSUFFICIENT_HISTORY'}
    n = len(prices)
    bounds = [int(n * x) for x in (.55, .70, .85, 1)]
    experiments = []
    # Predeclared variants: no optimization or selection based on holdout results.
    for hold in HOLDS:
        for filtered in (False, True):
            key = f"trend__hold_{hold}bars__" + ('strong_entry' if filtered else 'baseline')
            folds = []
            for i in range(3):
                train_end, test_end = bounds[i:i + 2]
                training = metrics(prices, WARMUP, train_end, category, 'trend', hold, filtered)
                holdout = metrics(prices, train_end, test_end, category, 'trend', hold, filtered)
                eligible = (training['completed_trades'] >= MIN_TRADES
                            and training['return_pct'] > MIN_RETURN
                            and training['max_drawdown_pct'] < MAX_DRAWDOWN
                            and training['execution_drag_pct_points'] <= MAX_DRAG
                            and training['win_rate_pct'] is not None
                            and training['win_rate_pct'] >= MIN_WIN_RATE)
                folds.append({'training': training, 'holdout_diagnostic_only': holdout,
                              'passes_original_training_filters': eligible,
                              'training_bars': train_end - WARMUP,
                              'holdout_bars': test_end - train_end})
            experiments.append({'configuration': key, 'folds': folds})
    return {'symbol': symbol, 'status': 'EXPERIMENTAL_ONLY',
            'experiments': experiments, 'approved_for_trading': False}


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('market_snapshot.json')
    snapshot = json.loads(path.read_text(encoding='utf-8'))
    result = {'version': '3.0', 'mode': 'research-only; no orders',
              'source_generated_at': snapshot.get('generated_at'),
              'holding_bars': list(HOLDS),
              'original_training_filters': {'min_completed_trades': MIN_TRADES,
                  'min_return_pct_exclusive': MIN_RETURN,
                  'max_drawdown_pct_exclusive': MAX_DRAWDOWN,
                  'max_execution_drag_pct_points': MAX_DRAG,
                  'min_win_rate_pct': MIN_WIN_RATE},
              'warning': ('Predeclared variants, diagnostic holdouts only; overlapping '
                          'training folds and sequential holdouts are not independent. '
                          'No strategy is approved for trading. Hourly close fills, '
                          'fixed costs and slippage are approximations.'),
              'results': [evaluate(m) for m in snapshot['markets']]}
    Path('research_experiments_v30.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    for r in result['results']:
        print(f"{r['symbol']}: {r['status']}; experimental only, no orders")
    print('Saved research_experiments_v30.json')


if __name__ == '__main__':
    main()
