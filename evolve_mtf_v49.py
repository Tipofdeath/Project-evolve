"""EVOLVE 4.9 independent multi-timeframe prospective paper experiment.
Completed 1h trend, completed 15m trigger, next observed 15m open.
No live orders; no retroactive simulated trades.
"""
import json, math, os
from pathlib import Path
from datetime import datetime, timezone
import requests
from evolve_shared import AUTO_MARKETS, metadata, FORWARD_FEE, FORWARD_SLIPPAGE

STATE=Path('mtf_state_v49.json')
REPORT=Path('mtf_report_v49.json')
COST=(1-FORWARD_FEE)*(1-FORWARD_SLIPPAGE)
VERSION='4.9-mtf'
def fetch(session,symbol,now):
    cutoff=now//900*900
    r=session.get('https://api.exchange.coinbase.com/products/'+symbol+'/candles',
       params={'granularity':900},headers={'User-Agent':'EVOLVE-MTF-paper/4.9'},timeout=30)
    r.raise_for_status()
    raw=r.json()
    if not isinstance(raw,list):raise ValueError('bad candle payload')
    d={}
    for c in raw:
        if not isinstance(c,list) or len(c)<6:continue
        t=int(c[0])
        if t>=cutoff or t%900:continue
        lo,hi,op,cl=map(float,c[1:5])
        if not all(math.isfinite(v) and v>0 for v in (lo,hi,op,cl)):continue
        if not lo<=min(op,cl)<=max(op,cl)<=hi:continue
        d[t]={'t':t,'o':op,'h':hi,'l':lo,'c':cl}
    bars=[d[t] for t in sorted(d)]
    if len(bars)<160 or any(b['t']-a['t']!=900 for a,b in zip(bars,bars[1:])):
        raise ValueError('insufficient or discontinuous completed 15m candles')
    return bars

def hourly(history):
    groups={}
    for b in history:
        t=b['t']//3600*3600
        groups.setdefault(t,[]).append(b)
    result=[]
    for t in sorted(groups):
        group=groups[t]
        if len(group)==4 and [x['t'] for x in group]==[t+i*900 for i in range(4)]:
            result.append({'t':t,'c':group[-1]['c']})
    return result

def ema(values,n):
    v=sum(values[:n])/n
    for x in values[n:]:v+=(2/(n+1))*(x-v)
    return v

def decide(history):
    # Only fully completed hourly bars; exclude the current partial hour.
    hrs=[h for h in hourly(history) if h['t']+3600<=history[-1]['t']+900]
    if len(hrs)<30 or len(history)<30:return False,0.,'warmup'
    prices=[h['c'] for h in hrs]
    fast=ema(prices,8);slow=ema(prices,21)
    if fast<=slow*1.002:return False,0.,'hourly_not_bullish'
    # Buy on 15m close above preceding 12-bar high, with modest volatility filter.
    upper=max(x['h'] for x in history[-13:-1])
    prev=history[-1]
    tr=[max(x['h']-x['l'],abs(x['h']-history[i-1]['c']),
            abs(x['l']-history[i-1]['c'])) for i,x in enumerate(history)
            if i>=len(history)-14]
    atr=sum(tr)/len(tr)
    if atr<=0 or atr/prev['c']>0.035:return False,atr,'volatility_filter'
    return prev['c']>upper,atr,'15m_breakout' if prev['c']>upper else 'no_15m_trigger'

def new(t):
    return {'cash':1.,'qty':0.,'basis':0.,'entry_time':None,'stop':None,
            'last_time':t,'peak':1.,'max_drawdown_pct':0.,'trades':[]}

def advance(p,bar,prior,reason):
    t=bar['t'];op=bar['o'];lo=bar['l'];cl=bar['c']
    if t<=p['last_time']:return
    closed=False
    def exit_at(price,why):
        nonlocal closed
        proceeds=p['qty']*price*COST
        p['cash']+=proceeds
        p['trades'].append({'entry_time':p['entry_time'],'exit_time':t,
            'pnl':round(proceeds-p['basis'],9),'reason':why})
        p.update(qty=0.,basis=0.,entry_time=None,stop=None)
        closed=True
    if p['qty']:
        if op<=p['stop']:exit_at(op*.995,'gap_stop')
        elif lo<=p['stop']:exit_at(p['stop']*.995,'stop_touch')
        elif t-p['entry_time']>=96*900:exit_at(op,'max_hold')
    if not p['qty'] and not closed and prior[0]:
        atr=prior[1]
        stop=op-max(2.5*atr,.012*op)
        if stop>0:
            basis=p['cash']*.15
            p['cash']-=basis
            p['qty']=basis*COST/op
            p['basis']=basis
            p['entry_time']=t
            p['stop']=stop
            # Intrabar sequence unknown; assume stop touched if bar low breaches it.
            if lo<=stop:exit_at(stop*.995,'entry_bar_stop_assumed')
    if p['qty']:
        # Trailing stop only effective for subsequent bars.
        p['stop']=max(p['stop'],cl*.97)
    equity=p['cash']+p['qty']*cl
    low_equity=p['cash']+p['qty']*lo
    p['max_drawdown_pct']=max(p['max_drawdown_pct'],
       100*(p['peak']-min(equity,low_equity))/p['peak'])
    p['peak']=max(p['peak'],equity)
    p['last_time']=t

def run():
    exists=STATE.exists()
    state=json.loads(STATE.read_text()) if exists else {'version':VERSION,'portfolios':{}}
    if state.get('version')!=VERSION:raise ValueError('incompatible state version')
    results=[];errors=[];now=int(datetime.now(timezone.utc).timestamp())
    with requests.Session() as s:
        for symbol in AUTO_MARKETS:
            try:
                bars=fetch(s,symbol,now)
                p=state['portfolios'].get(symbol)
                if p is None:
                    if exists:raise ValueError('missing portfolio from existing state')
                    p=new(bars[-1]['t'])
                else:
                    if p['last_time']<bars[0]['t']:raise ValueError('missing bars: no invented fills')
                    for i,b in enumerate(bars):
                        if b['t']>p['last_time']:
                            if i<160:raise ValueError('insufficient historical context')
                            active,atr,reason=decide(bars[:i])
                            advance(p,b,(active,atr),reason)
                state['portfolios'][symbol]=p
                active,atr,reason=decide(bars)
                equity=p['cash']+p['qty']*bars[-1]['c']
                results.append({'symbol':symbol,'last_15m_utc':
                    datetime.fromtimestamp(p['last_time'],timezone.utc).isoformat(),
                    'hourly_trend_and_15m_entry':reason,'entry_signal':active,
                    'open_position':bool(p['qty']),'closed_trades':len(p['trades']),
                    'return_pct':round((equity-1)*100,4),
                    'max_drawdown_pct':round(p['max_drawdown_pct'],4)})
            except (requests.RequestException,ValueError,KeyError,TypeError,IndexError,ZeroDivisionError) as e:
                errors.append({'symbol':symbol,'error':str(e)})
    if errors:
        # Do not overwrite the last good state when any market fails.
        REPORT.write_text(json.dumps({'version':VERSION,'results':results,'errors':errors,
            'approved_for_trading':False},indent=2)+'\n')
        return 1
    STATE.write_text(json.dumps(state,indent=2)+'\n')
    REPORT.write_text(json.dumps({'version':VERSION,'integration':metadata('mtf-paper'),
        'timeframes':['1h trend','15m entry and management'],'results':results,
        'errors':[],'approved_for_trading':False,
        'limitations':['Experimental strategy, not validated for profit',
         'Coinbase 15m candles only; missing bars fail closed',
         'Intrabar execution sequence and stop fills are approximations',
         'State must persist; no real orders or wallets']},indent=2)+'\n')
    return 0

if __name__=='__main__':raise SystemExit(run())
