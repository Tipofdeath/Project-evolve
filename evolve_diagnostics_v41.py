"""EVOLVE 4.1: explain rejected baseline opportunities; research only."""
import json
from pathlib import Path
import requests
from evolve_execution_v36 import fetch_ohlc,signal,SYMBOLS
from evolve_compare_v40 import features,simulate

def rejection_reasons(state):
    reasons=[]
    if state['daily']!='bullish':reasons.append('daily_not_bullish')
    if not state['discount']:reasons.append('not_discount')
    if state['weekly']!='bullish':reasons.append('weekly_not_bullish')
    return reasons

def diagnostic(candles,start,end):
    """Observe baseline trade entry dates, then classify filters without altering trades."""
    if not 40<=start<end<=len(candles):raise ValueError('invalid window')
    states=features(candles)
    # Reconstruct baseline entry calendar with the identical conservative execution
    # mechanics. Each baseline entry is a counterfactual opportunity, not an SMC trade.
    closes=[float(c['close']) for c in candles]
    entry=None;entry_bar=None;opportunities=[]
    for i in range(start,end):
        c=candles[i];opening=float(c['open']);low=float(c['low'])
        exited=False
        if entry is not None and (i-entry_bar>=60 or opening<=entry*.94):
            entry=None;entry_bar=None;exited=True
        if entry is None and not exited and i<end-1 and signal(closes,i):
            entry=opening;entry_bar=i
            reasons=rejection_reasons(states[i])
            opportunities.append({'entry_bar':i,'entry_date':c['time'][:10],
                 'daily':states[i]['daily'],'weekly':states[i]['weekly'],
                 'discount':states[i]['discount'],
                 'daily_smc_accepts':not any(x in reasons for x in ('daily_not_bullish','not_discount')),
                 'weekly_smc_accepts':not reasons,'rejection_reasons':reasons})
        if entry is not None and low<=entry*.94:
            entry=None;entry_bar=None
    base=simulate(candles,states,start,end,'baseline')
    if len(opportunities)!=base['entries']:
        raise ValueError('baseline entry calendar mismatch')
    counts={key:sum(key in o['rejection_reasons'] for o in opportunities)
            for key in ('daily_not_bullish','not_discount','weekly_not_bullish')}
    return {'baseline_entries':len(opportunities),
            'daily_smc_accepted_baseline_entries':sum(o['daily_smc_accepts'] for o in opportunities),
            'weekly_smc_accepted_baseline_entries':sum(o['weekly_smc_accepts'] for o in opportunities),
            'rejection_reason_counts_overlapping':counts,
            'baseline':base,'baseline_opportunities':opportunities,
            'note':'Counts describe filters at baseline entry times only. They do not equal SMC trade counts because skipped trades alter cash availability and timing.'}

def main():
    report={'version':'4.1','mode':'research-only; no orders','approved_for_trading':False,
            'purpose':'Audit why EVOLVE 4.0 SMC gates reject baseline entries',
            'limitations':['Rejection reasons overlap; do not sum them.',
                'Baseline entry dates are conditional on baseline position occupancy.',
                'No individual rejected-trade profitability attribution yet.',
                'Existing periods were used in development; not independent validation.',
                'No new strategy optimized or approved.'],
            'results':[],'errors':[]}
    with requests.Session() as session:
        for symbol in SYMBOLS:
            try:
                candles,q=fetch_ohlc(session,symbol)
                if q['status']!='PASS':raise ValueError('data quality failed')
                n=len(candles);bounds=[int(n*x) for x in (.55,.70,.85,1)]
                report['results'].append({'symbol':symbol,'quality':q,
                    'folds':[{'period':j+1,'diagnostics':diagnostic(candles,bounds[j],bounds[j+1])}
                             for j in range(3)]})
            except (requests.RequestException,ValueError,KeyError,TypeError) as exc:
                report['errors'].append({'symbol':symbol,'error':str(exc)})
    Path('smc_diagnostics_v41.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return 0 if len(report['results'])==len(SYMBOLS) and not report['errors'] else 1

if __name__=='__main__':raise SystemExit(main())
