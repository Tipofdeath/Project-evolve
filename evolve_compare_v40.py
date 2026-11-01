"""EVOLVE 4.0: predeclared causal SMC-filter comparison. Research only."""
import json
from pathlib import Path
import requests
from evolve_execution_v36 import fetch_ohlc,signal,SYMBOLS
from evolve_backtest_v28 import COST,SLIPPAGE
from evolve_smc_v38 import detect
from evolve_smc_context_v39 import completed_weekly

VARIANTS=('baseline','daily_smc','daily_weekly_smc')

def features(candles):
    """All decisions for entry at open i use information through close i-1."""
    d=detect(candles)
    highs={p['confirmed_at']:p['price'] for p in d['pivot_highs']}
    lows={p['confirmed_at']:p['price'] for p in d['pivot_lows']}
    events={}
    for e in d['events']:
        if e['type'] in ('BOS','CHoCH_candidate','structure_break'):
            events[e['bar']]=e['direction']
    weekly=completed_weekly(candles)
    w=detect(weekly) if len(weekly)>5 else {'events':[]}
    w_events={e['bar']:e['direction'] for e in w['events'] if e['type'] in ('BOS','CHoCH_candidate','structure_break')}
    # Week candle is known at its Sunday close. Entries are at the following open.
    weeks_by_day={c['time'][:10]:j for j,c in enumerate(weekly)}
    result=[];daily='unknown';higher='unknown';hi=None;lo=None;wi=-1
    for i,c in enumerate(candles):
        prior=i-1
        if prior in highs:hi=highs[prior]
        if prior in lows:lo=lows[prior]
        if prior in events:daily=events[prior]
        if prior>=0:
            date=candles[prior]['time'][:10]
            if date in weeks_by_day:
                new_wi=weeks_by_day[date]
                for j in range(wi+1,new_wi+1):
                    if j in w_events:higher=w_events[j]
                wi=new_wi
        price=float(candles[prior]['close']) if prior>=0 else None
        discount=(hi is not None and lo is not None and hi>lo and price<(hi+lo)/2)
        result.append({'daily':daily,'weekly':higher,'discount':discount})
    return result

def simulate(candles,feature_rows,start,end,variant,slippage_factor=1):
    if variant not in VARIANTS or not 40<=start<end<=len(candles):raise ValueError('invalid window/variant')
    closes=[float(c['close']) for c in candles]
    fee=COST['crypto'];slip=SLIPPAGE['crypto']*slippage_factor
    cash=1.;qty=0.;basis=0.;entry=0.;entry_bar=None;peak=1.;drawdown=0.;ledger=[];entries=0
    def exit_trade(price,i,reason):
        nonlocal cash,qty,basis,entry,entry_bar
        proceeds=qty*price*(1-fee)*(1-slip)
        ledger.append({'entry_bar':entry_bar,'exit_bar':i,'reason':reason,
                       'net_pnl':proceeds-basis})
        cash+=proceeds;qty=0.;basis=0.;entry=0.;entry_bar=None
    for i in range(start,end):
        c=candles[i];op=float(c['open']);low=float(c['low']);cl=float(c['close'])
        exited=False
        if qty and i-entry_bar>=60:
            exit_trade(op,i,'hold_open');exited=True
        elif qty and op<=entry*.94:
            exit_trade(op*.995,i,'gap_stop');exited=True
        # signal uses closes strictly before i, with no future data
        eligible=signal(closes,i)
        state=feature_rows[i]
        if variant=='daily_smc':eligible=eligible and state['daily']=='bullish' and state['discount']
        if variant=='daily_weekly_smc':eligible=eligible and state['daily']=='bullish' and state['weekly']=='bullish' and state['discount']
        if not qty and not exited and i<end-1 and eligible:
            basis=cash*.25;cash-=basis
            qty=basis*(1-fee)*(1-slip)/op
            entry=op;entry_bar=i;entries+=1
        if qty and low<=entry*.94:
            exit_trade(entry*.94*.995,i,'intraday_stop')
        equity_low=cash+qty*low
        drawdown=max(drawdown,(peak-equity_low)/peak)
        equity_close=cash+qty*cl
        peak=max(peak,equity_close)
        drawdown=max(drawdown,(peak-equity_close)/peak)
    if qty:exit_trade(float(candles[end-1]['close']),end-1,'window_end')
    pnl=sum(t['net_pnl'] for t in ledger)
    return {'return_pct':round((cash-1)*100,3),
            'max_drawdown_pct':round(drawdown*100,3),
            'trades':len(ledger),'entries':entries,
            'ledger_reconciles':abs(pnl-(cash-1))<1e-8}

def main():
    report={'version':'4.0','approved_for_trading':False,'mode':'research-only; no orders',
            'predeclared_variants':{
                'baseline':'Legacy entry signal, 25% allocation, 60d hold, 6% stop',
                'daily_smc':'Baseline AND bullish daily structure AND discount to latest confirmed swing midpoint',
                'daily_weekly_smc':'Daily SMC AND bullish completed-week structure'},
            'method':'Prior-close signals; next-open entry; conservative 0.5% adverse stop fill; 3 fixed chronological holdouts; 1x/3x slippage',
            'limitations':['Same historical data used in earlier EVOLVE development; not truly untouched holdouts.',
                           'Daily OHLC cannot resolve exact intraday order.',
                           'SMC filter definitions are hypotheses; no optimized thresholds or statistical significance.',
                           'Low trade counts can make comparisons unreliable.'],
            'results':[],'errors':[]}
    with requests.Session() as session:
        for symbol in SYMBOLS:
            try:
                candles,q=fetch_ohlc(session,symbol)
                if q['status']!='PASS':raise ValueError('data quality failed')
                f=features(candles);n=len(candles);bounds=[int(n*x) for x in (.55,.70,.85,1)]
                folds=[]
                for j in range(3):
                    variants={}
                    for v in VARIANTS:
                        variants[v]={'base':simulate(candles,f,bounds[j],bounds[j+1],v),
                                     'triple_slippage':simulate(candles,f,bounds[j],bounds[j+1],v,3)}
                    folds.append({'period':j+1,'variants':variants})
                report['results'].append({'symbol':symbol,'quality':q,'folds':folds})
            except (requests.RequestException,ValueError,KeyError,TypeError) as exc:
                report['errors'].append({'symbol':symbol,'error':str(exc)})
    Path('smc_comparison_v40.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return 0 if len(report['results'])==len(SYMBOLS) and not report['errors'] and all(
        x['ledger_reconciles'] for r in report['results'] for f in r['folds']
        for v in f['variants'].values() for x in v.values()) else 1

if __name__=='__main__':raise SystemExit(main())
