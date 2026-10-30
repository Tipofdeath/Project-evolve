"""EVOLVE 3.2: independent longer-history Coinbase crypto research.

Coinbase Exchange supports 1d and 6h candles (not native 4h). Do not
resample or fabricate candles. Strict gaps quarantine each market/timeframe.
No broker orders; no strategy approval.
"""
import json
import math
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
import requests
from evolve_risk_v31 import evaluate

SYMBOLS = ('BTC-USD', 'ETH-USD', 'SOL-USD')
FRAMES = (('6h', 21600, 2 * 365 * 4), ('1d', 86400, 5 * 365))
MAX_WINDOW = 250


def fetch(session, symbol, seconds, bars, now):
    end = datetime.fromtimestamp(int(now.timestamp()) // seconds * seconds, timezone.utc)
    rows = {}
    for _ in range((bars + MAX_WINDOW - 1) // MAX_WINDOW):
        start = end - timedelta(seconds=seconds * MAX_WINDOW)
        response = session.get(
            f'https://api.exchange.coinbase.com/products/{symbol}/candles',
            params={'granularity': seconds, 'start': start.isoformat(), 'end': end.isoformat()},
            headers={'User-Agent': 'Project-EVOLVE-3.2-research-only'},
            timeout=45,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise ValueError('unexpected exchange response')
        for item in payload:
            if isinstance(item, list) and len(item) >= 5:
                stamp, close = int(item[0]), float(item[4])
                if math.isfinite(close) and close > 0:
                    rows[stamp] = close
        end = start
        time.sleep(.25)
    stamps = sorted(rows)[-bars:]
    candles = [{'time': datetime.fromtimestamp(t, timezone.utc).isoformat(),
                'close': rows[t]} for t in stamps]
    gaps = sum((b - a) // seconds - 1 for a, b in zip(stamps, stamps[1:]))
    aligned = all(t % seconds == 0 for t in stamps)
    status = ('PASS' if len(stamps) == bars and gaps == 0 and aligned
              else 'QUARANTINED_INCOMPLETE_OR_GAPPED_HISTORY')
    return candles, {'status': status, 'requested_bars': bars,
                     'received_bars': len(stamps), 'missing_bars': gaps,
                     'aligned': aligned,
                     'first': candles[0]['time'] if candles else None,
                     'last': candles[-1]['time'] if candles else None}


def main():
    output = {'version': '3.2', 'mode': 'research-only; no orders',
              'note': ('Coinbase-native 6-hour and daily candles, with 2-year and '
                       '5-year target spans respectively. Not 4-hour candles. '
                       'Close-based stop thresholds and fixed costs remain hypothetical. '
                       'No strategy selection or trading authorization.'),
              'results': [], 'errors': []}
    now = datetime.now(timezone.utc)
    with requests.Session() as session:
        for symbol in SYMBOLS:
            for frame, seconds, bars in FRAMES:
                try:
                    candles, quality = fetch(session, symbol, seconds, bars, now)
                    entry = {'symbol': symbol, 'timeframe': frame,
                             'history_quality': quality, 'approved_for_trading': False}
                    if quality['status'] == 'PASS':
                        analysis = evaluate({'symbol': symbol, 'market': 'crypto',
                                             'candles': candles})
                        entry['research'] = analysis
                    else:
                        entry['research_status'] = 'SKIPPED_BAD_DATA'
                    output['results'].append(entry)
                    print(symbol, frame, quality['status'], quality['received_bars'])
                except (requests.RequestException, ValueError, TypeError, KeyError) as exc:
                    output['errors'].append({'symbol': symbol, 'timeframe': frame,
                                             'error': str(exc)})
                    print(symbol, frame, 'FAILED', str(exc))
    Path('extended_history_v32.json').write_text(json.dumps(output, indent=2), encoding='utf-8')
    print('Saved extended_history_v32.json')
    # Fail loudly if no datasets were validated.
    return 0 if any(x['history_quality']['status'] == 'PASS' for x in output['results']) else 2


if __name__ == '__main__':
    raise SystemExit(main())
