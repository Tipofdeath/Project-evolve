"""EVOLVE 3.7 conservative OHLC stress tests; research only, no orders."""
import json
from datetime import datetime,timezone
from pathlib import Path
import requests
from evolve_execution_v36 import fetch_ohlc,signal,SYMBOLS
from evolve_backtest_v28 import COST,SLIPPAGE

def simulate(candles,start,end,hold=60,allocation=.25,stop=.06,slippage_factor=1.,stop_impact=.005):
    if not 40<=start<end<=len(candles):raise ValueError('invalid window')
    if not (0<allocation<=1 and 0<stop<1 and hold>=1 and 0<=slippage_factor<=20 and 0<=stop_impact<1):
        raise ValueError('invalid parameters')
    for c in candles:
        lo,hi,op,cl=[float(c[k]) for k in ('low','high','open','close')]
        if not (0<lo<=min(op,cl)<=max(op,cl)<=hi):raise ValueError('invalid OHLC')
    closes=[float(c['close']) for c in candles]
    fee=COST['crypto'];slip=SLIPPAGE['crypto']*slippage_factor
    cash=1.;qty=0.;entry=None;entry_bar=None;basis=0.;peak=1.;dd=0.;ledger=[];worst_intraday=1.
    def sell(price,bar,reason):
        nonlocal cash,qty,entry,entry_bar,basis
        proceeds=qty*price*(1-fee)*(1-slip)
        pnl=proceeds-basis
        ledger.append({'entry_bar':entry_bar,'exit_bar':bar,'entry_price':entry,
                       'exit_price':price,'exit_reason':reason,'cost_basis':round(basis,10),
                       'net_proceeds':round(proceeds,10),'net_pnl':round(pnl,10)})
        cash+=proceeds
        qty=0.;entry=None;entry_bar=None;basis=0.
    for i in range(start,end):
        c=candles[i];op,lo,hi,cl=[float(c[k]) for k in ('open','low','high','close')]
        exited=False
        # Opening fills occur before the day's low/high. Hold expiry takes precedence at open.
        if qty and i-entry_bar>=hold:
            sell(op,i,'hold_at_open');exited=True
        elif qty:
            threshold=entry*(1-stop)
            if op<=threshold:
                sell(op*(1-stop_impact),i,'gap_stop_at_open');exited=True
        if not qty and not exited and i<end-1 and signal(closes,i):
            basis=cash*allocation;cash-=basis
            qty=basis*(1-fee)*(1-slip)/op
            entry=op;entry_bar=i
        # For entry-day low, open precedes low, so a stop may trigger.
        # Low-touch exits assume a stop-market order with an extra adverse fill haircut.
        if qty and lo<=entry*(1-stop):
            sell(entry*(1-stop)*(1-stop_impact),i,'intraday_stop_stressed');exited=True
        # Conservative low mark for an open position; do not infer exact intraday path.
        low_equity=cash+qty*lo
        worst_intraday=min(worst_intraday,low_equity)
        dd=max(dd,(peak-low_equity)/peak)
        closing_equity=cash+qty*cl
        peak=max(peak,closing_equity)
        dd=max(dd,(peak-closing_equity)/peak)
    if qty:
        sell(float(candles[end-1]['close']),end-1,'end_of_window_close')
        dd=max(dd,(peak-cash)/peak)
    pnl=sum(t['net_pnl'] for t in ledger)
    return {'return_pct':round((cash-1)*100,3),'max_drawdown_pct':round(dd*100,3),
            'trades':len(ledger),'entry_day_stop_exits':sum(t['exit_bar']==t['entry_bar'] and t['exit_reason']=='intraday_stop_stressed' for t in ledger),
            'gap_stop_exits':sum(t['exit_reason']=='gap_stop_at_open' for t in ledger),
            'ledger_reconciles':abs(pnl-(cash-1))<1e-7,'ledger':ledger}

def main():
    report={'version':'3.7','approved_for_trading':False,'mode':'research-only; no orders',
            'execution_assumptions':['Prior-close signal, next-day open entry.',
                'Entry-day low can trigger stop; exact intraday sequencing unknown.',
                'Stop-market fills assume threshold less 0.5% adverse impact; gaps fill below open by 0.5%.',
                'Mark-to-low drawdown is a conservative bound, not a time-ordered equity curve.',
                'Fixed 25% allocation, 60-day hold; not prospective validation.'],
            'results':[],'errors':[]}
    with requests.Session() as session:
        for symbol in SYMBOLS:
            try:
                candles,quality=fetch_ohlc(session,symbol)
                item={'symbol':symbol,'quality':quality,'approved_for_trading':False}
                if quality['status']=='PASS':
                    n=len(candles);bounds=[int(n*x) for x in (.55,.70,.85,1)]
                    item['folds']=[{'period':j+1,
                        'base':simulate(candles,bounds[j],bounds[j+1]),
                        'triple_slippage':simulate(candles,bounds[j],bounds[j+1],slippage_factor=3)}
                        for j in range(3)]
                    item['all_ledgers_reconcile']=all(f[k]['ledger_reconciles'] for f in item['folds'] for k in ('base','triple_slippage'))
                report['results'].append(item)
            except (requests.RequestException,ValueError,TypeError,KeyError) as e:
                report['errors'].append({'symbol':symbol,'error':str(e)})
    Path('conservative_execution_v37.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return 0 if len(report['results'])==3 and not report['errors'] and all(x.get('all_ledgers_reconcile') for x in report['results']) else 1

if __name__=='__main__':raise SystemExit(main())
