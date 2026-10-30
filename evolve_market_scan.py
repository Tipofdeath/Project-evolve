"""Project EVOLVE 2.0: read-only multi-market scanner.

Requires: requests, TWELVE_DATA_API_KEY in environment.
Outputs market_snapshot.json. Does not place trades or modify EVOLVE database.
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

API = 'https://api.twelvedata.com/time_series'
SYMBOLS = [('forex', 'EUR/USD'), ('forex', 'GBP/USD'), ('forex', 'USD/JPY'), ('gold', 'XAU/USD')]
COINBASE = [('crypto', 'BTC-USD'), ('crypto', 'ETH-USD'), ('crypto', 'SOL-USD')]


def twelve_candles(session, symbol, key):
    response = session.get(API, params={'symbol': symbol, 'interval': '1h', 'outputsize': 30, 'apikey': key}, timeout=25)
    response.raise_for_status()
    payload = response.json()
    if payload.get('status') == 'error' or 'values' not in payload:
        raise ValueError(f"Twelve Data: {payload.get('message', 'no candle data')}")
    result = []
    for item in payload['values']:
        close = float(item['close'])
        if close <= 0:
            continue
        result.append({'time': item['datetime'], 'close': close})
    return sorted(result, key=lambda x: x['time'])


def coinbase_candles(session, symbol):
    response = session.get(f'https://api.exchange.coinbase.com/products/{symbol}/candles', params={'granularity': 3600}, headers={'User-Agent': 'Project-EVOLVE-2-paper-scanner'}, timeout=25)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise ValueError('Coinbase did not return candles')
    result = []
    for item in payload:
        if isinstance(item, list) and len(item) >= 5 and float(item[4]) > 0:
            result.append({'time': datetime.fromtimestamp(int(item[0]), timezone.utc).isoformat(), 'close': float(item[4])})
    return sorted(result, key=lambda x: x['time'])[-30:]


def main():
    key = os.getenv('TWELVE_DATA_API_KEY')
    if not key:
        print('Missing TWELVE_DATA_API_KEY secret', file=sys.stderr)
        return 1
    output = {'generated_at': datetime.now(timezone.utc).isoformat(), 'mode': 'read-only paper trading research', 'markets': [], 'errors': []}
    with requests.Session() as session:
        for category, symbol in COINBASE + SYMBOLS:
            try:
                candles = coinbase_candles(session, symbol) if category == 'crypto' else twelve_candles(session, symbol, key)
                if len(candles) < 20:
                    raise ValueError(f'Insufficient history: {len(candles)} candles')
                output['markets'].append({'market': category, 'symbol': symbol, 'latest': candles[-1], 'candles': candles})
                print(f'OK {category:6} {symbol:8} latest={candles[-1]["close"]} candles={len(candles)}')
            except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
                output['errors'].append({'market': category, 'symbol': symbol, 'error': str(exc)})
                print(f'FAILED {symbol}: {exc}', file=sys.stderr)
    Path('market_snapshot.json').write_text(json.dumps(output, indent=2), encoding='utf-8')
    print(f'Saved market_snapshot.json: {len(output["markets"])} markets, {len(output["errors"])} errors')
    return 0 if len(output['markets']) == len(COINBASE) + len(SYMBOLS) else 2


if __name__ == '__main__':
    sys.exit(main())
