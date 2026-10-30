"""EVOLVE 3.1 risk-control sensitivity study. Research only; no orders.

Predeclared close-only stop scenarios and fractional allocation. All variants
are diagnostic; historical holdouts never authorize trades or select a winner.
"""
import json
import math
import sys
from pathlib import Path
from evolve_backtest_v28 import COST, SLIPPAGE, THRESHOLDS, WARMUP, MIN_BARS, mean, market_regime

HOLDS = (24, 48)
ALLOCATIONS = (0.25, 0.5)
STOP_PCTS = (0.03, 0.06)
COST_MULTIPLIERS = (1.0, 2.0)
LIMITS = {'min_completed_trades': 20, 'min_training_return_pct_exclusive': 1,
          'max_drawdown_pct_exclusive': 8, 'max_execution_drag_pct_points': 10,
          'min_win_rate_pct': 30}


def run(prices, start, end, category, hold, allocation, stop_pct, cost_multiplier=1.0):
    """Prior-close signals; current-close fills. Stops trigger on CLOSE only.

    Fixed fractional equity allocation; uninvested cash remains idle.
    No same-bar reentry, no intrabar fills, no leverage.
    """
    cfg = THRESHOLDS[category]
    side_cost = 1 - (1 - COST[category]) * (1 - SLIPPAGE[category])
    side_cost *= cost_multiplier
    if not 0 <= side_cost < 1:
        raise ValueError('invalid execution cost')
    cash, units, entry, entry_bar = 1.0, 0.0, None, None
    peak, max_dd, orders, wins, trades = 1.0, 0.0, 0, 0, 0
    for i in range(start, end):
        price = prices[i]
        if units:
            # Close-only stops can gap beyond the threshold.
            exit_now = (i - entry_bar >= hold or price <= entry * (1 - stop_pct))
            if exit_now:
                proceeds = units * price * (1 - side_cost)
                wins += proceeds > entry_value
                cash += proceeds
                units = 0.0
                orders += 1
                trades += 1
                entry = entry_bar = None
        elif i < end - 1:
            past = prices[:i]
            strong_trend = (mean(past[-10:]) > mean(past[-30:]) * (1 + cfg['trend'] * 2)
                            and past[-1] > mean(past[-10:]))
            if strong_trend and market_regime(prices, i, cfg) == 'trending':
                entry_value = cash * allocation
                cash -= entry_value
                units = entry_value * (1 - side_cost) / price
                entry, entry_bar = price, i
                orders += 1
        equity = cash + units * price
        peak = max(peak, equity)
        max_dd = max(max_dd, (peak - equity) / peak)
    if units:
        proceeds = units * prices[end - 1] * (1 - side_cost)
        wins += proceeds > entry_value
        cash += proceeds
        orders += 1
        trades += 1
        max_dd = max(max_dd, (peak - cash) / peak)
    return {'return_pct': round((cash - 1) * 100, 3),
            'max_drawdown_pct': round(max_dd * 100, 3),
            'completed_trades': trades, 'orders': orders,
            'win_rate_pct': round(100 * wins / trades, 2) if trades else None}


def evaluate(m):
    symbol, category = m.get('symbol'), m.get('market')
    if category not in THRESHOLDS:
        return {'symbol': symbol, 'status': 'INVALID_CATEGORY', 'approved_for_trading': False}
    try:
        candles = m['candles']
        times = [str(c['time']) for c in candles]
        prices = [float(c['close']) for c in candles]
        if not prices or any(not math.isfinite(p) and p > 0 for p in prices):
            raise ValueError('invalid prices')
        if times != sorted(times) or len(times) != len(set(times)):
            raise ValueError('invalid timestamps')
    except (KeyError, TypeError, ValueError) as e:
        return {'symbol': symbol, 'status': 'INVALID_DATA',
                'reason': str(e), 'approved_for_trading': False}
    if len(prices) < MIN_BARS:
        return {'symbol': symbol, 'status': 'INSUFFICIENT_HISTORY',
                'approved_for_trading': False}
    n = len(prices)
    boundaries = [int(n * f) for f in (.55, .70, .85, 1)]
    scenarios = []
    for hold in HOLDS:
        for allocation in ALLOCATIONS:
            for stop in STOP_PCTS:
                folds = []
                for i in range(3):
                    train_end, test_end = boundaries[i:i + 2]
                    train = run(prices, WARMUP, train_end, category, hold, allocation, stop)
                    train_zero = run(prices, WARMUP, train_end, category, hold, allocation, stop, 0)
                    train['execution_drag_pct_points'] = round(train_zero['return_pct'] - train['return_pct'], 3)
                    passes = (train['completed_trades'] >= LIMITS['min_completed_trades']
                              and train['return_pct'] > LIMITS['min_training_return_pct_exclusive']
                              and train['max_drawdown_pct'] < LIMITS['max_drawdown_pct_exclusive']
                              and train['execution_drag_pct_points'] <= LIMITS['max_execution_drag_pct_points']
                              and train['win_rate_pct'] is not None
                              and train['win_rate_pct'] >= LIMITS['min_win_rate_pct'])
                    holdout = run(prices, train_end, test_end, category, hold, allocation, stop)
                    stressed = run(prices, train_end, test_end, category, hold, allocation, stop, 2)
                    benchmark = round((prices[test_end - 1] / prices[train_end] - 1) * 100, 3)
                    folds.append({'training': train, 'passes_original_training_filters': passes,
                                  'holdout_diagnostic_only': holdout,
                                  'holdout_double_cost': stressed,
                                  'holdout_buy_and_hold_pct': benchmark,
                                  'holdout_excess_return_vs_buy_and_hold_pct_points':
                                      round(holdout['return_pct'] - benchmark, 3),
                                  'training_bars': train_end - WARMUP,
                                  'holdout_bars': test_end - train_end})
                scenarios.append({'hold_bars': hold, 'allocation_fraction': allocation,
                                  'close_only_stop_pct': stop * 100, 'folds': folds})
    return {'symbol': symbol, 'status': 'EXPERIMENTAL_ONLY',
            'approved_for_trading': False, 'scenarios': scenarios}


def main():
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('market_snapshot.json')
    data = json.loads(source.read_text(encoding='utf-8'))
    report = {'version': '3.1', 'mode': 'research-only; no orders',
              'source_generated_at': data.get('generated_at'),
              'original_training_filters': LIMITS,
              'caveats': [
                  'No strategies are approved for live trading.',
                  'Stops are tested at hourly closes only; gaps and intrabar losses can be larger.',
                  'Fractional allocation reduces exposure but does not guarantee risk limits.',
                  'Buy-and-hold is 100% exposure and is not allocation matched.',
                  'Costs and doubled costs are hypothetical scenarios, not actual broker fills.',
                  'Historical folds overlap in training; holdouts are diagnostic only.',
                  'No funding, spread dynamics, intrabar execution, taxes or market impact.',
              ],
              'results': [evaluate(m) for m in data['markets']]}
    Path('risk_validation_v31.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    for r in report['results']:
        print(f"{r['symbol']}: {r['status']}; trading approval disabled")
    print('Saved risk_validation_v31.json')


if __name__ == '__main__':
    main()
