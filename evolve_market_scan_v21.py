"""Project EVOLVE 2.1: read-only historical scanner.

Requires requests and TWELVE_DATA_API_KEY. Produces market_snapshot.json
in the same schema as EVOLVE 2.0. Does not place orders.
"""
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

API = 'https://api.twelvedata.com/time_series'
SYMBOLS = [('forex', 'EUR/USD'), ('forex', 'GBP/USD'), ('forex', 'USD/JPY'), ('gold', 'XAU/USD')]
COINBASE = [('crypto', 'BTC-USD'), ('crypto', 'ETH-USD'), ('crypto', 'SOL-USD')]
# Start modestly to avoid unexpectedly consuming Twelve Data credits.
TD_BARS = int(os.getenv('EVOLVE_TD_BARS', '500'))
CRYPTO_BARS = int(os.getenv('EVOLVE_CRYPTO_BARS', '750'))


def parse_td_time(value):
    """Twelve Data timestamps requested in UTC; label naive values accordingly."""
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def twelve_candles(session, symbol, key):
    response = session.get(API, params={
        'symbol': symbol, 'interval': '1h', 'outputsize': TD_BARS,
        'timezone': 'UTC', 'apikey': key,
    }, timeout=30)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or payload.get('status') == 'error' or 'values' not in payload:
        message = payload.get('message', 'no candle data') if isinstance(payload, dict) else 'unexpected response'
        raise ValueError(f'Twelve Data {symbol}: {message}')
    result = {}
    for item in payload['values']:
        price = float(item['close'])
        if price > 0:
            stamp = parse_td_time(item['datetime'])
            result[stamp] = {'time': stamp, 'close': price}
    return [result[k] for k in sorted(result)]


def coinbase_candles(session, symbol):
    """Page backward in windows of 250 hours; Coinbase caps responses at 300 bars."""
    result = {}
    end = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    windows = (CRYPTO_BARS + 249) // 250
    for _ in range(windows):
        start = end - timedelta(hours=250)
        response = session.get(
            f'https://api.exchange.coinbase.com/products/{symbol}/candles',
            params={'granularity': 3600, 'start': start.isoformat(), 'end': end.isoformat()},
            headers={'User-Agent': 'Project-EVOLVE-2.1-paper-scanner'}, timeout=30)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise ValueError(f'Coinbase {symbol}: unexpected response')
        for item in payload:
            if isinstance(item, list) and len(item) >= 5 and float(item[4]) > 0:
                stamp = datetime.fromtimestamp(int(item[0]), timezone.utc).isoformat()
                result[stamp] = {'time': stamp, 'close': float(item[4])}
        end = start
        time.sleep(0.25)
    return [result[k] for k in sorted(result)][-CRYPTO_BARS:]


def main():
    key = os.getenv('TWELVE_DATA_API_KEY')
    if not key:
        print('Missing TWELVE_DATA_API_KEY secret', file=sys.stderr)
        return 1
    if not 30 <= TD_BARS <= 5000 or not 30 <= CRYPTO_BARS <= 2000:
        print('Bar counts outside allowed ranges', file=sys.stderr)
        return 1
    output = {'generated_at': datetime.now(timezone.utc).isoformat(),
              'mode': 'read-only paper trading research', 'markets': [], 'errors': []}
    with requests.Session() as session:
        for category, symbol in COINBASE + SYMBOLS:
            try:
                candles = (coinbase_candles(session, symbol) if category == 'crypto'
                           else twelve_candles(session, symbol, key))
                if len(candles) < 35:
                    raise ValueError(f'Only {len(candles)} candles received (need at least 35)')
                output['markets'].append({'market': category, 'symbol': symbol,
                                          'latest': candles[-1], 'candles': candles})
                print(f'OK {category:6} {symbol:8} latest={candles[-1]["close"]} candles={len(candles)}')
            except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
                output['errors'].append({'market': category, 'symbol': symbol, 'error': str(exc)})
                print(f'FAILED {symbol}: {exc}', file=sys.stderr)
    Path('market_snapshot.json').write_text(json.dumps(output, indent=2), encoding='utf-8')
    print(f'Saved market_snapshot.json: {len(output["markets"])} markets, {len(output["errors"])} errors')
    return 0 if len(output['markets']) == len(COINBASE) + len(SYMBOLS) else 2


if __name__ == '__main__':
    sys.exit(main())
