"""EVOLVE 4.4: crypto-only strategy reliability audit; research only."""
import json
from pathlib import Path
import requests
from evolve_execution_v36 import fetch_ohlc, SYMBOLS
from evolve_validation_v43 import analyze

def audit_symbol(symbol, candles, quality):
    if quality.get('status') != 'PASS':
        raise ValueError('unverified OHLC')
    result = analyze(candles)
    folds = []
    for fold in result['folds']:
        variants = {}
        for name, modes in fold['variants'].items():
            normal, stress = modes['normal'], modes['triple_slippage']
            variants[name] = {
                'normal': normal,
                'triple_slippage': stress,
                'stress_return_delta_pct': round(stress['return_pct'] - normal['return_pct'], 3),
                'stress_worsened_return': stress['return_pct'] < normal['return_pct'],
                'zero_trades': normal['trades'] == 0,
                'ledger_reconciles': normal['ledger_reconciles'] and stress['ledger_reconciles']
            }
            if not variants[name]['ledger_reconciles']:
                raise ValueError('trade ledger does not reconcile')
        folds.append({'period': fold['period'], 'start': fold['start'],
                      'end': fold['end'], 'variants': variants})
    return {'symbol': symbol, 'quality': quality, 'causal_audit': result['audit'],
            'summary': result['summary'], 'folds': folds}

def main():
    report = {
        'version': '4.4', 'mode': 'research-only; no orders',
        'approved_for_trading': False, 'asset_scope': 'crypto-only',
        'purpose': 'Auditable historical fold reliability and slippage sensitivity',
        'limitations': [
            'Same previously examined historical folds; NOT untouched out-of-sample.',
            'Triple-slippage is a scenario, not a calibrated execution-cost estimate.',
            'Daily OHLC cannot resolve intraday stop order or real execution prices.',
            'Causal audit checks breakout indicators at selected prefixes only.',
            'No forward paper-trading evidence; no proof of future profitability.'
        ], 'results': [], 'errors': []
    }
    with requests.Session() as session:
        for symbol in SYMBOLS:
            try:
                candles, quality = fetch_ohlc(session, symbol)
                report['results'].append(audit_symbol(symbol, candles, quality))
            except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
                report['errors'].append({'symbol': symbol, 'error': str(exc)})
    report['complete'] = len(report['results']) == len(SYMBOLS) and not report['errors']
    Path('crypto_reliability_v44.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return 0 if report['complete'] else 1

if __name__ == '__main__':
    raise SystemExit(main())
