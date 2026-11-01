"""EVOLVE 4.5: append-only prospective crypto signal log; no orders."""
import json
import os
from pathlib import Path
from datetime import datetime, timezone
import requests
from evolve_execution_v36 import SYMBOLS, fetch_ohlc, signal
from evolve_breakout_v42 import indicators

STATE=Path('forward_state_v45.json')
REPORT=Path('forward_report_v45.json')
def run():
    state=json.loads(STATE.read_text()) if STATE.exists() else {'version':'4.5','created_at':datetime.now(timezone.utc).isoformat(),'events':[]}
    events=state['events']
    known={(e['symbol'],e['strategy'],e['signal_day']) for e in events}
    results=[];errors=[]
    with requests.Session() as session:
        for symbol in SYMBOLS:
            try:
                candles,q=fetch_ohlc(session,symbol)
                if q['status']!='PASS':raise ValueError('unverified OHLC')
                day=candles[-1]['time'][:10]
                closes=[float(c['close']) for c in candles]
                # Signal at the last COMPLETED UTC close, never enter on that bar.
                i=len(candles)
                original=signal(closes,i)
                # indicators[i] is the decision for the open of bar i, using closes through i-1.
                # Compute with a dummy next bar, never using its values in indicators[i].
                dummy=dict(candles[-1]);states=indicators(candles+[dummy])
                breakout=states[i] is not None and states[i]['prior_close']>states[i]['upper']
                for strategy,active in [('original',original),('breakout',breakout)]:
                    key=(symbol,strategy,day)
                    if key not in known:
                        events.append({'symbol':symbol,'strategy':strategy,'signal_day':day,
                                       'signal':bool(active),'reference_close':candles[-1]['close'],
                                       'next_open':None,'next_open_day':None})
                        known.add(key)
                # Only resolve a prior signal once its following completed daily bar is available.
                by_day={c['time'][:10]:c for c in candles}
                ordered=sorted(by_day)
                for e in events:
                    if e['symbol']!=symbol or e.get('next_open') is not None:continue
                    if e['signal_day'] not in by_day:continue
                    idx=ordered.index(e['signal_day'])
                    if idx+1<len(ordered):
                        next_c=by_day[ordered[idx+1]]
                        e['next_open']=next_c['open']
                        e['next_open_day']=next_c['time'][:10]
                results.append({'symbol':symbol,'quality':q,'last_completed_day':day,
                                'original_signal':bool(original),'breakout_signal':bool(breakout)})
            except (requests.RequestException,ValueError,KeyError,TypeError,IndexError) as exc:
                errors.append({'symbol':symbol,'error':str(exc)})
    # Never backfill historic signals: only log signals first observed after tracking began.
    state['events']=events
    STATE.write_text(json.dumps(state,indent=2)+'\n')
    report={'version':'4.5','approved_for_trading':False,'mode':'signals-only; no orders',
            'created_at':state['created_at'],'run_at':datetime.now(timezone.utc).isoformat(),
            'results':results,'events_total':len(events),
            'pending_next_open':sum(e['next_open'] is None for e in events),
            'errors':errors,'limitations':[
                'Signals recorded at daily completed close; next open is observed later, not a guaranteed fill.',
                'No positions, PnL, stop orders or trade execution are simulated yet.',
                'Persistence requires restored state across workflow runs; missing state starts a new cohort.',
                'No orders, credentials, deposits, or real trading.']}
    REPORT.write_text(json.dumps(report,indent=2)+'\n')
    return 0 if len(results)==len(SYMBOLS) and not errors else 1
if __name__=='__main__':raise SystemExit(run())
