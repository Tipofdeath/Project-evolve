"""EVOLVE 4.6 prospective, research-only paper trading; never places orders."""
import json
from pathlib import Path
from datetime import date
import requests
from evolve_execution_v36 import SYMBOLS,fetch_ohlc
from evolve_shared import FORWARD_FEE as FEE, FORWARD_SLIPPAGE as SLIP, metadata
def fresh(day):
    return {'cash':1.,'qty':0.,'basis':0.,'entry':None,'entry_day':None,'stop':None,
            'atr':None,'last_day':day,'peak':1.,'max_dd':0.,'trades':[]}
def step(p,c,prior_signal,strategy):
    day=c['time'][:10]
    if day<=p['last_day']:return
    op,lo,cl=(float(c[k]) for k in ('open','low','close'))
    exited=False
    def sell(price,reason):
        nonlocal exited
        proceeds=p['qty']*price*(1-FEE)*(1-SLIP)
        p['cash']+=proceeds
        p['trades'].append({'entry_day':p['entry_day'],'exit_day':day,'reason':reason,
                            'pnl':round(proceeds-p['basis'],9)})
        p.update(qty=0.,basis=0.,entry=None,entry_day=None,stop=None,atr=None)
        exited=True
    if p['qty']:
        age=(date.fromisoformat(day)-date.fromisoformat(p['entry_day'])).days
        if op<=p['stop']:sell(op*.995,'gap_stop')
        elif lo<=p['stop']:sell(p['stop']*.995,'stop_touch')
        elif strategy=='original' and age>=60:sell(op,'hold_open')
    if not p['qty'] and not exited and prior_signal and prior_signal['signal']:
        atr=prior_signal.get('atr')
        if strategy=='breakout' and (atr is None or atr<=0):
            raise ValueError('missing ATR for prospective breakout signal')
        p['basis']=p['cash']*.25;p['cash']-=p['basis']
        p['qty']=p['basis']*(1-FEE)*(1-SLIP)/op
        p['entry']=op;p['entry_day']=day;p['atr']=atr
        p['stop']=op*.94 if strategy=='original' else op-3*atr
    if p['qty']:
        if lo<=p['stop']:sell(p['stop']*.995,'entry_day_stop_assumed')
        elif strategy=='breakout':p['stop']=max(p['stop'],cl-3*p['atr'])
    low_equity=p['cash']+p['qty']*lo
    p['max_dd']=max(p['max_dd'],100*(p['peak']-low_equity)/p['peak'])
    equity=p['cash']+p['qty']*cl
    p['peak']=max(p['peak'],equity)
    p['max_dd']=max(p['max_dd'],100*(p['peak']-equity)/p['peak'])
    p['last_day']=day
def run():
    history_path=Path('forward_state_v45.json')
    if not history_path.exists():raise ValueError('Missing signal history: no historical reconstruction allowed')
    history=json.loads(history_path.read_text())
    path=Path('paper_state_v46.json')
    state=json.loads(path.read_text()) if path.exists() else {'version':'4.6','portfolios':{}}
    results=[];errors=[]
    with requests.Session() as session:
        for symbol in SYMBOLS:
            try:
                candles,q=fetch_ohlc(session,symbol)
                if q['status']!='PASS':raise ValueError('bad OHLC quality')
                days={c['time'][:10]:c for c in candles}
                for strategy in ('original','breakout'):
                    key=symbol+'|'+strategy
                    sigs={e['signal_day']:e for e in history['events']
                          if e['symbol']==symbol and e['strategy']==strategy}
                    p=state['portfolios'].get(key)
                    if p is None:p=fresh(min(sigs) if sigs else candles[-1]['time'][:10])
                    if p['last_day']<candles[0]['time'][:10]:raise ValueError('missing historical bars')
                    for c in candles:
                        day=c['time'][:10]
                        if day<=p['last_day']:continue
                        previous=date.fromordinal(date.fromisoformat(day).toordinal()-1).isoformat()
                        step(p,c,sigs.get(previous),strategy)
                    state['portfolios'][key]=p
                    equity=p['cash']+p['qty']*float(candles[-1]['close'])
                    results.append({'symbol':symbol,'strategy':strategy,
                        'last_day':p['last_day'],'completed_trades':len(p['trades']),
                        'open_position':p['qty']>0,'return_pct':round(100*(equity-1),4),
                        'max_drawdown_pct':round(p['max_dd'],4)})
            except (requests.RequestException,ValueError,KeyError,TypeError) as exc:
                errors.append({'symbol':symbol,'error':str(exc)})
    path.write_text(json.dumps(state,indent=2)+'\n')
    Path('paper_report_v46.json').write_text(json.dumps({'version':'4.6',
        'approved_for_trading':False,'mode':'research-only; no orders',
        'integration':metadata('daily-forward'),
        'results':results,'errors':errors,
        'limitations':['No backfilled signals or real orders.',
          'Daily OHLC cannot establish intraday order or executable prices.',
          '0.5% adverse stop-fill assumption plus estimated fees and slippage.',
          'Separate normalized hypothetical portfolios, not a combined account.',
          'State must be restored across runs for valid forward testing.']},indent=2)+'\n')
    return 0 if len(results)==6 and not errors else 1
if __name__=='__main__':raise SystemExit(run())
