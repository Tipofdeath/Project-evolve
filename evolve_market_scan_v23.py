"""Project EVOLVE 2.3: read-only hourly historical scanner.

Produces market_snapshot.json compatible with EVOLVE 2.1 and a separate
market_data_quality.json diagnostics file. Never places orders.
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
TD_BARS = int(os.getenv('EVOLVE_TD_BARS', '2160'))
CRYPTO_BARS = int(os.getenv('EVOLVE_CRYPTO_BARS', '2160'))


def utc_stamp(value):
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def twelve_candles(session, symbol, key):
    response = session.get(API, params={
        'symbol': symbol, 'interval': '1h', 'outputsize': TD_BARS,
        'timezone': 'UTC', 'apikey': key,
    }, timeout=45)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or payload.get('status') == 'error' or 'values' not in payload:
        message = payload.get('message', 'no candle data') if isinstance(payload, dict) else 'unexpected response'
        raise ValueError(f'Twelve Data {symbol}: {message}')
    rows = []
    for item in payload['values']:
        price = float(item['close'])
        if price > 0:
            rows.append({'time': utc_stamp(item['datetime']), 'close': price})
    return rows


def coinbase_candles(session, symbol):
    """Fetch consecutive 250-hour windows; Coinbase permits up to 300 bars/request."""
    rows = []
    end = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    windows = (CRYPTO_BARS + 249) // 250
    for _ in range(windows):
        start = end - timedelta(hours=250)
        response = session.get(
            f'https://api.exchange.coinbase.com/products/{symbol}/candles',
            params={'granularity': 3600, 'start': start.isoformat(), 'end': end.isoformat()},
            headers={'User-Agent': 'Project-EVOLVE-2.3-research-scanner'}, timeout=45)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise ValueError(f'Coinbase {symbol}: unexpected response')
        for item in payload:
            if isinstance(item, list) and len(item) >= 5 and float(item[4]) > 0:
                rows.append({'time': datetime.fromtimestamp(int(item[0]), timezone.utc).isoformat(),
                             'close': float(item[4])})
        end = start
        time.sleep(0.3)
    return rows


def clean_and_measure(rows, category, symbol, requested):
    unique = {}
    duplicates = 0
    off_hour = 0
    for row in rows:
        stamp = utc_stamp(row['time'])
        dt = datetime.fromisoformat(stamp)
        if dt.minute or dt.second:
            off_hour += 1
        if stamp in unique:
            duplicates += 1
        unique[stamp] = {'time': stamp, 'close': float(row['close'])}
    candles = [unique[k] for k in sorted(unique)]
    missing_hours = 0
    weekend_missing_hours = 0
    largest_gap_hours = 0
    for left, right in zip(candles, candles[1:]):
        start = datetime.fromisoformat(left['time'])
        end = datetime.fromisoformat(right['time'])
        hours = int((end - start).total_seconds() // 3600)
        largest_gap_hours = max(largest_gap_hours, hours)
        if hours > 1:
            for h in range(1, hours):
                missing = start + timedelta(hours=h)
                if category != 'crypto' and missing.weekday() >= 5:
                    weekend_missing_hours += 1
                else:
                    missing_hours += 1
    weekend_candles = sum(datetime.fromisoformat(c['time']).weekday() >= 5 for c in candles)
    diagnostics = {
        'weekend_candles': weekend_candles,
        'quality_status': 'BLOCKED_WEEKEND_CANDLES' if category != 'crypto' and weekend_candles else 'PASS',
        'market': category, 'symbol': symbol, 'requested_bars': requested,
        'raw_rows': len(rows), 'unique_candles': len(candles),
        'duplicate_rows': duplicates, 'off_hour_timestamps': off_hour,
        'missing_hours_excluding_weekends': missing_hours,
        'weekend_missing_hours': weekend_missing_hours,
        'largest_gap_hours': largest_gap_hours,
        'first_candle': candles[0]['time'] if candles else None,
        'last_candle': candles[-1]['time'] if candles else None,
        'span_calendar_days': round((datetime.fromisoformat(candles[-1]['time']) - datetime.fromisoformat(candles[0]['time'])).total_seconds() / 86400, 2) if len(candles) > 1 else 0,
        'note': 'Weekend classification is approximate; market holidays and daily FX session breaks may also create gaps.' if category != 'crypto' else 'Crypto normally trades continuously.'
    }
    return candles[-requested:], diagnostics


def main():
    key = os.getenv('TWELVE_DATA_API_KEY')
    if not key:
        print('Missing TWELVE_DATA_API_KEY secret', file=sys.stderr)
        return 1
    if not 30 <= TD_BARS <= 5000 or not 30 <= CRYPTO_BARS <= 5000:
        print('Bar counts outside allowed ranges (30..5000)', file=sys.stderr)
        return 1
    output = {'generated_at': datetime.now(timezone.utc).isoformat(),
              'mode': 'read-only paper trading research', 'markets': [], 'errors': []}
    quality = {'generated_at': output['generated_at'], 'requested_td_bars': TD_BARS,
               'requested_crypto_bars': CRYPTO_BARS, 'markets': [], 'errors': []}
    with requests.Session() as session:
        for category, symbol in COINBASE + SYMBOLS:
            try:
                raw = coinbase_candles(session, symbol) if category == 'crypto' else twelve_candles(session, symbol, key)
                requested = CRYPTO_BARS if category == 'crypto' else TD_BARS
                candles, diagnostics = clean_and_measure(raw, category, symbol, requested)
                if len(candles) < 35:
                    raise ValueError(f'Only {len(candles)} candles received (need at least 35)')
                quality['markets'].append(diagnostics)
                if diagnostics['quality_status'] != 'PASS':
                    issue = {'market': category, 'symbol': symbol,
                             'error': f'QUARANTINED: {diagnostics["weekend_candles"]} weekend candles in hourly feed; source requires verification'}
                    output['errors'].append(issue)
                    quality['errors'].append(issue)
                    print(f'BLOCKED {symbol}: {issue["error"]}', file=sys.stderr)
                    continue
                output['markets'].append({'market': category, 'symbol': symbol,
                                          'latest': candles[-1], 'candles': candles})
                print(f'OK {category:6} {symbol:8} candles={len(candles)} '
                      f'first={diagnostics["first_candle"]} last={diagnostics["last_candle"]} '
                      f'gaps={diagnostics["missing_hours_excluding_weekends"]}')
            except (requests.RequestException, ValueError, KeyError, TypeError, OverflowError) as exc:
                issue = {'market': category, 'symbol': symbol, 'error': str(exc)}
                output['errors'].append(issue)
                quality['errors'].append(issue)
                print(f'FAILED {symbol}: {exc}', file=sys.stderr)
    Path('market_snapshot.json').write_text(json.dumps(output, indent=2), encoding='utf-8')
    Path('market_data_quality.json').write_text(json.dumps(quality, indent=2), encoding='utf-8')
    print(f'Saved market_snapshot.json: {len(output["markets"])} markets, {len(output["errors"])} errors')
    # Allow a crypto-only research run; never include quarantined FX/gold in snapshot.
    # Nonzero exit if any crypto dataset is missing, so the workflow cannot quietly pass.
    present_crypto = {m['symbol'] for m in output['markets'] if m['market'] == 'crypto'}
    return 0 if present_crypto == {symbol for _, symbol in COINBASE} else 2


if __name__ == '__main__':
    sys.exit(main())
