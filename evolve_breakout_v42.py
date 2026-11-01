"""EVOLVE 4.2: independent Donchian/ATR trend strategy, research only."""
import json
from pathlib import Path
import requests
from evolve_execution_v36 import fetch_ohlc,SYMBOLS
from evolve_compare_v40 import features,simulate as baseline_simulate
from evolve_backtest_v28 import COST,SLIPPAGE

def indicators(candles,lookback=55,atr_period=20):
    """Decision at open i uses data strictly before i."""
    out=[]
    for i in range(len(candles)):
        if i<max(lookback,atr_period+1):
            out.append(None);continue
        prior=candles[:i]
        upper=max(float(x['high']) for x in prior[-lookback:])
        trs=[]
        for j in range(i-atr_period,i):
            x=candles[j];prev=float(candles[j-1]['close'])
            h=float(x['high']);l=float(x['low'])
            trs.append(max(h-l,abs(h-prev),abs(l-prev)))
        atr=sum(trs)/len(trs)
        out.append({'upper':upper,'atr':atr,'prior_close':float(candles[i-1]['close'])})
    return out

def simulate(candles,states,start,end,slippage_factor=1.,atr_multiple=3.):
    if not 60<=start<end<=len(candles) or len(states)!=len(candles):
        raise ValueError('invalid window/states')
    if atr_multiple<=0 or slippage_factor<0:raise ValueError('invalid costs/stop')
    fee=COST['crypto'];slip=SLIPPAGE['crypto']*slippage_factor
    if fee+slip>=1:raise ValueError('invalid costs')
    cash=1.;qty=0.;basis=0.;entry_bar=None;stop=None;peak=1.;dd=0.;ledger=[]
    def sell(price,i,reason):
        nonlocal cash,qty,basis,entry_bar,stop
        proceeds=qty*price*(1-fee)*(1-slip)
        ledger.append({'entry_bar':entry_bar,'exit_bar':i,'reason':reason,'net_pnl':proceeds-basis})
        cash+=proceeds;qty=0.;basis=0.;entry_bar=None;stop=None
    for i in range(start,end):
        c=candles[i];op=float(c['open']);lo=float(c['low']);cl=float(c['close'])
        state=states[i];exited=False
        if qty and op<=stop:
            sell(op*.995,i,'gap_stop');exited=True
        elif qty and lo<=stop:
            sell(stop*.995,i,'intraday_stop');exited=True
        # Breakout confirmed by prior close, enter at next open.
        if not qty and not exited and i<end-1 and state and state['prior_close']>state['upper']:
            basis=cash*.25;cash-=basis;qty=basis*(1-fee)*(1-slip)/op
            entry_bar=i;stop=op-atr_multiple*state['atr']
        if qty and lo<=stop:
            sell(stop*.995,i,'entry_day_stop')
        # Ratchet stop only AFTER today's price action, effective tomorrow.
        if qty and state:
            stop=max(stop,cl-atr_multiple*state['atr'])
        low_equity=cash+qty*lo
        dd=max(dd,(peak-low_equity)/peak)
        close_equity=cash+qty*cl;peak=max(peak,close_equity)
        dd=max(dd,(peak-close_equity)/peak)
    if qty:sell(float(candles[end-1]['close']),end-1,'window_end')
    pnl=sum(x['net_pnl'] for x in ledger)
    return {'return_pct':round((cash-1)*100,3),'max_drawdown_pct':round(dd*100,3),
            'trades':len(ledger),'ledger_reconciles':abs(pnl-(cash-1))<1e-8}

def main():
    report={'version':'4.2','mode':'research-only; no orders','approved_for_trading':False,
            'strategy':'55-day Donchian close breakout, 20-day ATR, 3x ATR trailing stop, 25% cash allocation',
            'method':'Previous-day confirmed breakout; next-open entry; entry-day and gap stop stress; 1x and 3x slippage; fixed prior folds',
            'limitations':['Historical periods were already used for EVOLVE development; not untouched out-of-sample.',
                           'Daily OHLC cannot establish exact intraday sequence or guaranteed stop fills.',
                           'A trailing stop updated after close becomes effective next day.',
                           'Parameters are hypotheses, not optimized or validated.'],
            'results':[],'errors':[]}
    with requests.Session() as session:
        for symbol in SYMBOLS:
            try:
                candles,q=fetch_ohlc(session,symbol)
                if q['status']!='PASS':raise ValueError('data quality failed')
                states=indicators(candles);base_states=features(candles)
                n=len(candles);bounds=[int(n*x) for x in (.55,.70,.85,1)]
                folds=[]
                for j in range(3):
                    a,b=bounds[j:j+2]
                    folds.append({'period':j+1,
                      'original':{'base':baseline_simulate(candles,base_states,a,b,'baseline'),
                                  'triple_slippage':baseline_simulate(candles,base_states,a,b,'baseline',3)},
                      'donchian_atr':{'base':simulate(candles,states,a,b),
                                      'triple_slippage':simulate(candles,states,a,b,3)}})
                report['results'].append({'symbol':symbol,'quality':q,'folds':folds})
            except (requests.RequestException,ValueError,KeyError,TypeError) as exc:
                report['errors'].append({'symbol':symbol,'error':str(exc)})
    Path('breakout_comparison_v42.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return 0 if len(report['results'])==len(SYMBOLS) and not report['errors'] and all(
        v['ledger_reconciles'] for x in report['results'] for f in x['folds']
        for strat in ('original','donchian_atr') for v in f[strat].values()) else 1
if __name__=='__main__':raise SystemExit(main())
