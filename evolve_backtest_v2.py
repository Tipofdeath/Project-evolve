"""Project EVOLVE 2.0: conservative, close-only research backtester.
Run: python evolve_backtest_v2.py [market_snapshot.json]
No orders or broker connections. Needs >= 100 hourly closes per symbol.
"""
import json
import math
import sys
from pathlib import Path

MIN_BARS = 100
FAST = 10
SLOW = 30
# Illustrative round-trip-independent per-side costs, NOT verified broker quotes.
SIDE_COST = {'crypto': 0.0025, 'forex': 0.0002, 'gold': 0.0005}


def evaluate(market):
    symbol = market['symbol']
    category = market['market']
    candles = market['candles']
    result = {'symbol': symbol, 'market': category, 'candles': len(candles)}
    try:
        times = [str(c['time']) for c in candles]
        prices = [float(c['close']) for c in candles]
        if any(not math.isfinite(p) or p <= 0 for p in prices):
            raise ValueError('invalid price')
        if times != sorted(times) or len(set(times)) != len(times):
            raise ValueError('timestamps not unique and increasing')
    except (KeyError, ValueError, TypeError) as exc:
        result.update(status='INVALID_DATA', reason=str(exc))
        return result
    if len(prices) < MIN_BARS:
        result.update(status='INSUFFICIENT_HISTORY', required=MIN_BARS,
                      reason='Collect more hourly closes before evaluating performance')
        return result
    # First 70% is warmup/development; report only the last 30% as a holdout.
    start = max(SLOW + 1, int(len(prices) * 0.7))
    cash, units, peak, worst_dd, trades = 1.0, 0.0, 1.0, 0.0, 0
    cost = SIDE_COST.get(category, 0.0025)
    for i in range(start, len(prices)):
        # Signal uses candles ending at i-1; execution uses close at i.
        fast = sum(prices[i-FAST:i]) / FAST
        slow = sum(prices[i-SLOW:i]) / SLOW
        price = prices[i]
        if fast > slow and units == 0:
            units = cash * (1-cost) / price
            cash = 0.0
            trades += 1
        elif fast < slow and units > 0:
            cash = units * price * (1-cost)
            units = 0.0
            trades += 1
        equity = cash + units * price
        peak = max(peak, equity)
        worst_dd = max(worst_dd, (peak-equity)/peak)
    final_equity = cash + units * prices[-1]
    result.update(status='EXPERIMENTAL_ONLY', holdout_bars=len(prices)-start,
                  strategy='10/30 SMA crossover, long/flat', orders=trades,
                  assumed_cost_per_side_pct=round(cost*100, 4),
                  return_pct=round((final_equity-1)*100, 3),
                  max_drawdown_pct=round(worst_dd*100, 3),
                  warning='Close-only fills are optimistic; no bid/ask, intrabar stops, or financing')
    return result


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('market_snapshot.json')
    data = json.loads(path.read_text(encoding='utf-8'))
    results = [evaluate(m) for m in data['markets']]
    output = {'source_generated_at': data.get('generated_at'),
              'mode': 'research-only, no orders', 'results': results}
    Path('backtest_report.json').write_text(json.dumps(output, indent=2), encoding='utf-8')
    for r in results:
        print(f"{r['symbol']}: {r['status']} ({r['candles']} bars)" +
              (f" | holdout return {r['return_pct']}%" if 'return_pct' in r else ''))
    print('Saved backtest_report.json')


if __name__ == '__main__':
    main()
