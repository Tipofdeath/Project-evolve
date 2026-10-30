"""Project EVOLVE 2.2: multi-strategy, research-only backtester.
Usage: python evolve_backtest_v22.py [market_snapshot.json]
No broker connections or live orders. Long/flat, close-only approximation.
"""
import json
import math
import statistics
import sys
from pathlib import Path

MIN_BARS = 180
SIDE_COST = {'crypto': 0.0025, 'forex': 0.0002, 'gold': 0.0005}
STRATEGIES = ('trend', 'momentum', 'breakout', 'mean_reversion')
WARMUP = 35


def mean(xs):
    return sum(xs) / len(xs)


def signal(strategy, prices, i):
    """Decision at i uses only bars through i-1. Returns long or flat."""
    h = prices[:i]
    if strategy == 'trend':
        return mean(h[-10:]) > mean(h[-30:]) * 1.001
    if strategy == 'momentum':
        return h[-1] > h[-13] * 1.015 and mean(h[-5:]) > mean(h[-20:])
    if strategy == 'breakout':
        return h[-1] > max(h[-21:-1])
    if strategy == 'mean_reversion':
        mu = mean(h[-20:])
        sd = statistics.pstdev(h[-20:])
        return sd > 0 and h[-1] < mu - 1.5 * sd
    return False


def backtest(prices, strategy, start, stop, cost):
    """Flat at start; execute next bar close after prior-bar signal.
    Every signal is a target position, not a permanent entry trigger.
    Force liquidation at the final close, including cost.
    """
    cash, units, peak, worst_dd, orders = 1.0, 0.0, 1.0, 0.0, 0
    for i in range(start, stop):
        price = prices[i]
        want_long = signal(strategy, prices, i)
        if want_long and units == 0:
            units = cash * (1 - cost) / price
            cash = 0.0
            orders += 1
        elif not want_long and units > 0:
            cash = units * price * (1 - cost)
            units = 0.0
            orders += 1
        equity = cash + units * price
        peak = max(peak, equity)
        worst_dd = max(worst_dd, (peak - equity) / peak)
    if units > 0:
        cash = units * prices[stop - 1] * (1 - cost)
        orders += 1
        worst_dd = max(worst_dd, (peak - cash) / peak)
    return {'return_pct': round((cash - 1) * 100, 3),
            'max_drawdown_pct': round(worst_dd * 100, 3),
            'orders': orders}


def evaluate(market):
    result = {'symbol': market.get('symbol'), 'market': market.get('market')}
    try:
        candles = market['candles']
        times = [str(c['time']) for c in candles]
        prices = [float(c['close']) for c in candles]
        if any(not math.isfinite(p) or p <= 0 for p in prices):
            raise ValueError('invalid price')
        if times != sorted(times) or len(set(times)) != len(times):
            raise ValueError('timestamps not unique and increasing')
    except (KeyError, ValueError, TypeError) as exc:
        result.update(status='INVALID_DATA', reason=str(exc))
        return result
    n = len(prices)
    result['candles'] = n
    if n < MIN_BARS:
        result.update(status='INSUFFICIENT_HISTORY', required=MIN_BARS)
        return result
    split = int(n * .7)
    cost = SIDE_COST.get(result['market'], 0.0025)
    training = {s: backtest(prices, s, WARMUP, split, cost) for s in STRATEGIES}
    # Select on training ONLY. Favor positive returns and lower drawdowns.
    def score(s):
        r = training[s]
        return r['return_pct'] - r['max_drawdown_pct']
    chosen = max(STRATEGIES, key=score)
    holdout = backtest(prices, chosen, split, n, cost)
    # All holdout comparisons are exploratory; only the chosen result is selection-safe.
    exploratory = {s: backtest(prices, s, split, n, cost) for s in STRATEGIES}
    benchmark = (prices[-1] / prices[split] - 1) * 100
    result.update(status='EXPERIMENTAL_ONLY', selected_strategy=chosen,
                  training_bars=split - WARMUP, holdout_bars=n - split,
                  training_results=training, selected_holdout=holdout,
                  exploratory_holdout=exploratory,
                  holdout_buy_hold_return_pct=round(benchmark, 3),
                  assumed_cost_per_side_pct=round(cost * 100, 4),
                  warning='Close-only execution; no spread quotes, financing, intrabar stops or broker validation. Short sample; selection is not proof of profitability.')
    return result


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('market_snapshot.json')
    data = json.loads(path.read_text(encoding='utf-8'))
    results = [evaluate(m) for m in data['markets']]
    output = {'source_generated_at': data.get('generated_at'),
              'mode': 'research-only; no orders', 'version': '2.2', 'results': results}
    Path('backtest_report_v22.json').write_text(json.dumps(output, indent=2), encoding='utf-8')
    for r in results:
        if r['status'] == 'EXPERIMENTAL_ONLY':
            h = r['selected_holdout']
            print(f"{r['symbol']}: {r['selected_strategy']} | holdout {h['return_pct']:+.3f}% | max DD {h['max_drawdown_pct']:.3f}% | orders {h['orders']}")
        else:
            print(f"{r['symbol']}: {r['status']}")
    print('Saved backtest_report_v22.json')


if __name__ == '__main__':
    main()
