"""EVOLVE 2.0 read-only, multi-market signal research.

Reads market_snapshot.json produced by evolve_market_scan.py.
Writes strategy_report.json; never trades or modifies SQLite.
Signals are experimental and are NOT profit forecasts.
"""
import json
import math
from datetime import datetime, timezone
from pathlib import Path

INPUT = Path('market_snapshot.json')
OUTPUT = Path('strategy_report.json')


def ema(values, period):
    if not values:
        return None
    alpha = 2 / (period + 1)
    value = values[0]
    for x in values[1:]:
        value = alpha * x + (1 - alpha) * value
    return value


def rsi(values, period=14):
    if len(values) < period + 1:
        return None
    changes = [values[i] - values[i - 1] for i in range(len(values) - period, len(values))]
    gain = sum(max(x, 0) for x in changes) / period
    loss = sum(max(-x, 0) for x in changes) / period
    if gain == 0 and loss == 0:
        return 50.0
    if loss == 0:
        return 100.0
    return 100 - 100 / (1 + gain / loss)


def evaluate(item):
    candles = item.get('candles', [])
    closes = [float(c['close']) for c in candles]
    if len(closes) < 26 or any(not math.isfinite(p) or p <= 0 for p in closes):
        return {'symbol': item.get('symbol'), 'decision': 'NO_DATA', 'reason': 'Need at least 26 valid hourly closes'}
    last = closes[-1]
    short = ema(closes, 8)
    long = ema(closes, 21)
    strength = (short / long - 1) * 100
    momentum = (last / closes[-7] - 1) * 100
    rsi_value = rsi(closes)
    changes = [math.log(b / a) for a, b in zip(closes[:-1], closes[1:])]
    vol = (sum(x * x for x in changes[-20:]) / 20) ** 0.5 * 100
    previous_high = max(closes[-21:-1])
    previous_low = min(closes[-21:-1])
    # A ranking heuristic only, not a calibrated probability of success.
    trend = 1 if strength > 0.15 else -1 if strength < -0.15 else 0
    mom = 1 if momentum > 0.25 else -1 if momentum < -0.25 else 0
    breakout = 1 if last > previous_high else -1 if last < previous_low else 0
    reversal = 1 if rsi_value < 30 else -1 if rsi_value > 70 else 0
    score = trend + mom + breakout + reversal
    # Forex typically has smaller percentage moves than crypto; this heuristic
    # is intentionally conservative and must be tuned only with out-of-sample tests.
    if abs(score) < 2:
        decision = 'WAIT'
    else:
        decision = 'RESEARCH_LONG' if score > 0 else 'RESEARCH_SHORT'
    return {
        'market': item.get('market'), 'symbol': item.get('symbol'),
        'latest_close': last, 'candles': len(closes), 'time': candles[-1].get('time'),
        'decision': decision, 'signal_score': score,
        'indicators': {'ema_8': round(short, 6), 'ema_21': round(long, 6),
                       'trend_gap_pct': round(strength, 4), 'momentum_6h_pct': round(momentum, 4),
                       'rsi_14': round(rsi_value, 2), 'hourly_volatility_pct': round(vol, 4)},
        'votes': {'trend': trend, 'momentum': mom, 'breakout': breakout, 'mean_reversion': reversal},
        'caveat': 'Research signal only; ignores execution spreads, swap, slippage, market hours, and broker pricing.'
    }


def main():
    data = json.loads(INPUT.read_text(encoding='utf-8'))
    results = [evaluate(item) for item in data.get('markets', [])]
    report = {'generated_at': datetime.now(timezone.utc).isoformat(),
              'source_snapshot': data.get('generated_at'),
              'mode': 'research only: no orders, no database writes',
              'results': results, 'feed_errors': data.get('errors', [])}
    OUTPUT.write_text(json.dumps(report, indent=2), encoding='utf-8')
    for item in results:
        print(f"{item['symbol']}: {item['decision']} (score={item.get('signal_score', 'n/a')})")
    print(f'Saved {OUTPUT}')


if __name__ == '__main__':
    main()
