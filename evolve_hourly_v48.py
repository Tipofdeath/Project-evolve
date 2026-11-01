"""Independent hourly EVOLVE paper experiment. Not the daily 4.6 strategy.
Uses completed Coinbase 1h OHLC, prior-bar signals, next-bar open, no live orders.
"""
import json, math, os
from datetime import datetime, timezone
from pathlib import Path
import requests
from evolve_shared import AUTO_MARKETS, metadata, FORWARD_FEE, FORWARD_SLIPPAGE

STATE=Path(os.getenv('EVOLVE_HOURLY_STATE','hourly_state_v48.json'))
REPORT=Path('hourly_report_v48.json')
FEE=FORWARD_FEE
SLIP=FORWARD_SLIPPAGE

def candles_for(session,symbol,now=None):
    if symbol not in AUTO_MARKETS: raise ValueError('unsupported market')
    now=int(now if now is not None else datetime.now(timezone.utc).timestamp())
    boundary=now//3600*3600
    resp=session.get('https://api.exchange.coinbase.com/products/'+symbol+'/candles',
        params={'granularity':3600},headers={'User-Agent':'EVOLVE-hourly-paper/4.8'},timeout=30)
    resp.raise_for_status()
    raw=resp.json()
    if not isinstance(raw,list):raise ValueError('invalid candle response')
    bars={}
    for row in raw:
        if not isinstance(row,list) or len(row)<6:continue
        t=int(row[0])
        if t>=boundary or t%3600:continue
        low,high,op,close=map(float,row[1:5])
        if not all(math.isfinite(x) and x>0 for x in (low,high,op,close)):continue
        if not low<=min(op,close)<=max(op,close)<=high:continue
        bars[t]={'time':t,'open':op,'high':high,'low':low,'close':close}
    ordered=[bars[t] for t in sorted(bars)]
    if len(ordered)<80 or any(b['time']-a['time']!=3600 for a,b in zip(ordered,ordered[1:])):
        raise ValueError('insufficient or discontinuous completed hourly candles')
    return ordered

def signal_for(history,strategy):
    if len(history)<60:return False,None
    closes=[c['close'] for c in history]
    if strategy=='original':
        avg10=sum(closes[-10:])/10
        avg30=sum(closes[-30:])/30
        return avg10>avg30*1.005 and closes[-1]>avg10,None
    if strategy!='breakout':raise ValueError('unknown strategy')
    upper=max(c['high'] for c in history[-56:-1])
    trs=[max(c['high']-c['low'],abs(c['high']-history[j-1]['close']),
             abs(c['low']-history[j-1]['close']))
         for j,c in enumerate(history) if j>=len(history)-20]
    atr=sum(trs)/len(trs)
    return closes[-1]>upper,atr

def fresh(t):
    return {'cash':1.,'qty':0.,'basis':0.,'entry':None,'entry_time':None,
            'stop':None,'atr':None,'last_time':t,'peak':1.,'max_dd':0.,'trades':[]}

def step(p,bar,history,strategy):
    t=bar['time']
    if t<=p['last_time']:return
    op,low,close=bar['open'],bar['low'],bar['close']
    exited=False
    def sell(price,reason):
        nonlocal exited
        proceeds=p['qty']*price*(1-FEE)*(1-SLIP)
        p['cash']+=proceeds
        p['trades'].append({'entry_time':p['entry_time'],'exit_time':t,
                            'reason':reason,'pnl':round(proceeds-p['basis'],9)})
        p.update(qty=0.,basis=0.,entry=None,entry_time=None,stop=None,atr=None)
        exited=True
    if p['qty']:
        age=(t-p['entry_time'])//3600
        if op<=p['stop']:sell(op*.995,'gap_stop')
        elif low<=p['stop']:sell(p['stop']*.995,'stop_touch')
        elif strategy=='original' and age>=60:sell(op,'hold_open')
    active,atr=signal_for(history,strategy)
    entered=False
    if not p['qty'] and not exited and active:
        if strategy=='breakout' and (atr is None or atr<=0):
            raise ValueError('invalid breakout ATR')
        basis=p['cash']*.25
        if basis>0:
            p['cash']-=basis
            p['qty']=basis*(1-FEE)*(1-SLIP)/op
            p['basis']=basis
            p['entry']=op
            p['entry_time']=t
            p['atr']=atr
            p['stop']=op*.94 if strategy=='original' else op-3*atr
            entered=True
    # On entry bar, OHLC cannot determine whether the low came before entry.
    # We conservatively model a stop touch, but it is an assumption.
    if entered and low<=p['stop']:
        sell(p['stop']*.995,'entry_bar_stop_assumed')
    if p['qty'] and strategy=='breakout':
        p['stop']=max(p['stop'],close-3*p['atr'])
    equity=p['cash']+p['qty']*close
    low_equity=p['cash']+p['qty']*low
    p['max_dd']=max(p['max_dd'],100*(p['peak']-min(equity,low_equity))/p['peak'])
    p['peak']=max(p['peak'],equity)
    p['last_time']=t

def run():
    state=json.loads(STATE.read_text()) if STATE.exists() else {'version':'4.8-hourly','portfolios':{}}
    if state.get('version')!='4.8-hourly':raise ValueError('unexpected hourly state version')
    results=[];errors=[]
    with requests.Session() as session:
        for symbol in AUTO_MARKETS:
            try:
                bars=candles_for(session,symbol)
                for strategy in ('original','breakout'):
                    key=symbol+'|'+strategy
                    p=state['portfolios'].get(key)
                    if p is None:
                        # Initialize at last completed candle; no historical simulated trades.
                        p=fresh(bars[-1]['time'])
                    else:
                        if p['last_time']<bars[0]['time']:
                            raise ValueError('missing hourly candles; refusing to invent fills')
                        for i,bar in enumerate(bars):
                            if bar['time']>p['last_time']:
                                step(p,bar,bars[:i],strategy)
                    state['portfolios'][key]=p
                    equity=p['cash']+p['qty']*bars[-1]['close']
                    results.append({'symbol':symbol,'strategy':strategy,
                        'last_hour_utc':datetime.fromtimestamp(p['last_time'],timezone.utc).isoformat(),
                        'closed_trades':len(p['trades']),'open_position':p['qty']>0,
                        'return_pct':round((equity-1)*100,4),
                        'max_drawdown_pct':round(p['max_dd'],4)})
            except (requests.RequestException,ValueError,KeyError,TypeError,IndexError) as exc:
                errors.append({'symbol':symbol,'error':str(exc)})
    STATE.write_text(json.dumps(state,indent=2)+'\n')
    report={'version':'4.8-hourly','integration':metadata('hourly-paper'),
        'timeframe':'1h','approved_for_trading':False,'results':results,'errors':errors,
        'limitations':['Hourly strategy parameters are experimental adaptations, not validated daily strategy results.',
          'First run initializes without retroactively inventing trades.',
          'Hourly OHLC cannot establish intrabar stop execution sequence.',
          'Missing bars quarantine the market; state must persist between runs.',
          'Paper-only; no orders or wallets.']}
    REPORT.write_text(json.dumps(report,indent=2)+'\n')
    return 0 if len(results)==6 and not errors else 1

if __name__=='__main__':raise SystemExit(run())
