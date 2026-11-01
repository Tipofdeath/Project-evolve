"""EVOLVE 4.3: chronological robustness and causal audit; no trading."""
import json
from pathlib import Path
import requests
from evolve_execution_v36 import fetch_ohlc,SYMBOLS
from evolve_breakout_v42 import indicators,simulate
from evolve_compare_v40 import features,simulate as original_simulate

FOLDS=(.55,.70,.85,1.0)

def causal_audit(candles,indices):
    """Recompute on prefixes; later candles must not change earlier signals."""
    full=indicators(candles)
    checked=[]
    for i in indices:
        prefix=indicators(candles[:i+1])
        if full[i]!=prefix[i]:raise ValueError('lookahead: breakout indicator changed with future data')
        checked.append(i)
    return {'checked_indices':checked,'passed':True}

def analyze(candles):
    n=len(candles)
    bounds=[int(n*x) for x in FOLDS]
    breakout=indicators(candles)
    baseline=features(candles)
    audit=causal_audit(candles,[bounds[0],bounds[1],bounds[2],n-1])
    folds=[]
    for j in range(3):
        a,b=bounds[j:j+2]
        variants={}
        for name,fn in (
            ('original',lambda factor:original_simulate(candles,baseline,a,b,'baseline',factor)),
            ('breakout',lambda factor:simulate(candles,breakout,a,b,factor))):
            variants[name]={'normal':fn(1),'triple_slippage':fn(3)}
            if not all(x['ledger_reconciles'] for x in variants[name].values()):
                raise ValueError('ledger mismatch')
        folds.append({'period':j+1,'start':candles[a]['time'],'end':candles[b-1]['time'],
                      'variants':variants})
    summary={}
    for name in ('original','breakout'):
        vals=[f['variants'][name]['normal'] for f in folds]
        stress=[f['variants'][name]['triple_slippage'] for f in folds]
        summary[name]={'profitable_periods':sum(v['return_pct']>0 for v in vals),
                       'losing_periods':sum(v['return_pct']<0 for v in vals),
                       'trades':sum(v['trades'] for v in vals),
                       'worst_fold_drawdown_pct':max(v['max_drawdown_pct'] for v in vals),
                       'triple_slippage_profitable_periods':sum(v['return_pct']>0 for v in stress)}
    return {'audit':audit,'folds':folds,'summary':summary}

def main():
    report={'version':'4.3','approved_for_trading':False,'mode':'research-only; no orders',
      'purpose':'Chronological fold comparison and prefix-causality audit across BTC ETH SOL',
      'method':'Fixed historical 55/70/85/100 percent chronological boundaries; no parameter fitting; prior-close signals and next-open fills',
      'limitations':['These historical folds are NOT untouched prospective or independent out-of-sample validation.',
        'Prefix invariance tests breakout indicator only, not all upstream SMC features or execution.',
        'Daily OHLC cannot establish intraday ordering; entry-day stops and 0.5% adverse fills are assumptions.',
        'Same historical observations used in prior EVOLVE development; no claim of proven profitability.'],
      'results':[],'errors':[]}
    with requests.Session() as session:
        for symbol in SYMBOLS:
            try:
                candles,q=fetch_ohlc(session,symbol)
                if q['status']!='PASS':raise ValueError('data quality failed')
                report['results'].append({'symbol':symbol,'quality':q,**analyze(candles)})
            except (requests.RequestException,ValueError,KeyError,TypeError) as exc:
                report['errors'].append({'symbol':symbol,'error':str(exc)})
    Path('validation_v43.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return 0 if len(report['results'])==len(SYMBOLS) and not report['errors'] else 1
if __name__=='__main__':raise SystemExit(main())
