"""EVOLVE 3.6: next-open execution and OHLC stop stress. Research only."""
import json
import math
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
import requests
from evolve_backtest_v28 import COST, SLIPPAGE, THRESHOLDS, market_regime

SYMBOLS=('BTC-USD','ETH-USD','SOL-USD')
BARS=1825
def fetch_ohlc(session,symbol,bars=BARS,now=None):
    now=now or datetime.now(timezone.utc)
    # Exclude current unfinished UTC day.
    end=datetime.fromtimestamp(int(now.timestamp())//86400*86400,timezone.utc)
    rows={}
    for _ in range((bars+249)//250):
        start=end-timedelta(days=250)
        response=session.get('https://api.exchange.coinbase.com/products/'+symbol+'/candles',
            params={'granularity':86400,'start':start.isoformat(),'end':end.isoformat()},
            headers={'User-Agent':'EVOLVE-3.6-research-only'},timeout=45)
        response.raise_for_status()
        data=response.json()
        if not isinstance(data,list): raise ValueError('invalid API response')
        for v in data:
            if not isinstance(v,list) or len(v)<6: continue
            stamp=int(v[0]); low,high,op,cl=map(float,(v[1],v[2],v[3],v[4]))
            if all(math.isfinite(x) and x>0 for x in (low,high,op,cl)) and low<=min(op,cl)<=max(op,cl)<=high:
                if stamp < int(now.timestamp())//86400*86400:
                    rows[stamp]={'time':datetime.fromtimestamp(stamp,timezone.utc).isoformat(),
                                 'open':op,'high':high,'low':low,'close':cl}
        end=start
        time.sleep(.25)
    stamps=sorted(rows)[-bars:]
    gaps=sum((b-a)//86400-1 for a,b in zip(stamps,stamps[1:]))
    quality={'status':'PASS' if len(stamps)==bars and gaps==0 and all(t%86400==0 for t in stamps) else 'QUARANTINED',
             'bars':len(stamps),'missing_bars':gaps,'first':rows[stamps[0]]['time'] if stamps else None,
             'last':rows[stamps[-1]]['time'] if stamps else None}
    return [rows[t] for t in stamps],quality

def signal(closes,i):
    cfg=THRESHOLDS['crypto']
    past=closes[:i]
    if len(past)<40:return False
    avg=lambda xs:sum(xs)/len(xs)
    return (avg(past[-10:])>avg(past[-30:])*(1+cfg['trend']*2)
            and past[-1]>avg(past[-10:]) and market_regime(closes,i,cfg)=='trending')

def simulate(candles,start,end,hold=60,allocation=.25,stop=.06,slippage_factor=1.):
    if not 40<=start<end<=len(candles):raise ValueError('invalid window')
    if not (0<allocation<=1 and 0<stop<1 and hold>=1 and slippage_factor>=0):
        raise ValueError('invalid parameters')
    closes=[float(c['close']) for c in candles]
    for c in candles:
        lo,hi,op,cl=(float(c[k]) for k in ('low','high','open','close'))
        if not all(math.isfinite(v) and v>0 for v in (lo,hi,op,cl)) or not lo<=min(op,cl)<=max(op,cl)<=hi:
            raise ValueError('invalid OHLC candle')
    fee=COST['crypto']; slip=SLIPPAGE['crypto']*slippage_factor
    if fee+slip>=1:raise ValueError('invalid execution cost')
    cash,qty,basis,entry,entry_bar=1.,0.,0.,None,None
    trades=[]; peak=1.;dd=0.;gap_stops=0
    # Signal at close of i-1, fill at open of i; no current-bar signal peeking.
    for i in range(start,end):
        c=candles[i];op,lo,cl=(float(c[k]) for k in ('open','low','close'))
        exited=False
        if qty:
            threshold=entry*(1-stop)
            if op<=threshold:
                exit_price=op;reason='gap_stop';gap_stops+=1
            elif lo<=threshold:
                exit_price=threshold;reason='intraday_stop_assumed'
            elif i-entry_bar>=hold:
                exit_price=op;reason='hold_open'
            else:
                exit_price=None;reason=None
            if exit_price is not None:
                proceeds=qty*exit_price*(1-fee)*(1-slip)
                cash+=proceeds
                trades.append({'entry_bar':entry_bar,'exit_bar':i,'entry_price':entry,
                               'exit_price':exit_price,'reason':reason,
                               'pnl_initial_equity_pct':round((proceeds-basis)*100,5)})
                qty=0.;entry=None;entry_bar=None;basis=0.;exited=True
        if not qty and not exited and i<end-1 and signal(closes,i):
            basis=cash*allocation
            cash-=basis
            qty=basis*(1-fee)*(1-slip)/op
            entry=op;entry_bar=i
            # Entry bar can cross stop after entry, but OHLC cannot reveal event ordering.
            # Do not claim an intrabar stop on entry day; mark it as unresolved.
        equity=cash+qty*cl
        peak=max(peak,equity)
        dd=max(dd,(peak-equity)/peak)
    if qty:
        exit_price=float(candles[end-1]['close'])
        proceeds=qty*exit_price*(1-fee)*(1-slip)
        cash+=proceeds
        trades.append({'entry_bar':entry_bar,'exit_bar':end-1,'entry_price':entry,
                       'exit_price':exit_price,'reason':'window_end_close',
                       'pnl_initial_equity_pct':round((proceeds-basis)*100,5)})
        dd=max(dd,(peak-cash)/peak)
    return {'return_pct':round((cash-1)*100,3),'max_drawdown_pct':round(dd*100,3),
            'trades':len(trades),'gap_stop_exits':gap_stops,'ledger':trades,
            'note':'Intraday stop fills at threshold are optimistic when liquidity/slippage deteriorates; entry-day intrabar order unknown.'}

def main():
    report={'version':'3.6','mode':'research-only','approved_for_trading':False,
            'method':'prior-close signal; next-open entry; gap-at-open stop; low-touch stop threshold (optimistic); open-time hold exit',
            'limitations':['Daily OHLC does not reveal intraday event ordering, especially on entry day.',
                           'Intraday stop fill at threshold is not guaranteed.',
                           'Same historical windows; not fresh prospective validation.',
                           'Not a paper-trading system; no live orders.'],
            'results':[],'errors':[]}
    with requests.Session() as session:
        for symbol in SYMBOLS:
            try:
                candles,q=fetch_ohlc(session,symbol)
                item={'symbol':symbol,'quality':q}
                if q['status']=='PASS':
                    n=len(candles);bounds=[int(n*f) for f in (.55,.70,.85,1)]
                    item['folds']=[{'period':j+1,
                        'base':simulate(candles,bounds[j],bounds[j+1]),
                        'triple_slippage':simulate(candles,bounds[j],bounds[j+1],slippage_factor=3)}
                        for j in range(3)]
                report['results'].append(item)
            except (requests.RequestException,ValueError,TypeError,KeyError) as exc:
                report['errors'].append({'symbol':symbol,'error':str(exc)})
    Path('execution_stress_v36.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return 0 if len(report['results'])==3 and not report['errors'] and all(x['quality']['status']=='PASS' for x in report['results']) else 1

if __name__=='__main__':
    raise SystemExit(main())
