"""EVOLVE 3.5 independent trade-ledger replay. Research only."""
import json
import math
from pathlib import Path
from datetime import datetime, timezone
import requests
from evolve_history_v32 import fetch
from evolve_backtest_v28 import COST, SLIPPAGE, THRESHOLDS
from evolve_audit_v34 import classify
from evolve_risk_v31 import run as legacy_run

def average(values):
    return sum(values) / len(values)

def replay(prices, start, end, hold=60, allocation=.25, stop=.06, multiplier=1):
    if not 90 <= start < end <= len(prices):
        raise ValueError('invalid window')
    if not 0 < allocation <= 1 or not 0 < stop < 1 or hold < 1:
        raise ValueError('invalid parameters')
    if any(not math.isfinite(p) or p <= 0 for p in prices):
        raise ValueError('invalid prices')
    side_cost = (1 - (1-COST['crypto'])*(1-SLIPPAGE['crypto'])) * multiplier
    if not 0 <= side_cost < 1:
        raise ValueError('invalid cost')
    cash, quantity, basis, entry_price, entry_index = 1., 0., 0., None, None
    peak, max_dd = 1., 0.
    trades, equity_curve = [], []
    cfg = THRESHOLDS['crypto']
    for i in range(start, end):
        price = prices[i]
        if quantity:
            reason = 'hold' if i-entry_index >= hold else ('close_stop' if price <= entry_price*(1-stop) else None)
            if reason:
                proceeds = quantity*price*(1-side_cost)
                cash += proceeds
                trades.append({'entry_bar':entry_index,'exit_bar':i,'entry_price':entry_price,
                               'exit_price':price,'entry_regime':classify(prices,entry_index),
                               'exit_reason':reason,'cost_basis':round(basis,10),
                               'net_proceeds':round(proceeds,10),
                               'net_pnl':round(proceeds-basis,10),
                               'net_pnl_pct_of_initial_equity':round((proceeds-basis)*100,6)})
                quantity, basis, entry_price, entry_index = 0., 0., None, None
        elif i < end-1:
            past = prices[:i]
            trend = average(past[-10:]) > average(past[-30:])*(1+cfg['trend']*2) and past[-1] > average(past[-10:])
            # Reproduce existing prior-close trend classification without using future bars.
            from evolve_backtest_v28 import market_regime
            if trend and market_regime(prices,i,cfg)=='trending':
                basis=cash*allocation
                cash-=basis
                quantity=basis*(1-side_cost)/price
                entry_price,entry_index=price,i
        equity=cash+quantity*price
        peak=max(peak,equity)
        max_dd=max(max_dd,(peak-equity)/peak)
        equity_curve.append(round(equity,10))
    if quantity:
        proceeds=quantity*prices[end-1]*(1-side_cost)
        cash+=proceeds
        trades.append({'entry_bar':entry_index,'exit_bar':end-1,'entry_price':entry_price,
                       'exit_price':prices[end-1],'entry_regime':classify(prices,entry_index),
                       'exit_reason':'end_of_window','cost_basis':round(basis,10),
                       'net_proceeds':round(proceeds,10),'net_pnl':round(proceeds-basis,10),
                       'net_pnl_pct_of_initial_equity':round((proceeds-basis)*100,6)})
        max_dd=max(max_dd,(peak-cash)/peak)
        equity_curve[-1]=round(cash,10)
    regime_stats={}
    for regime in ('bull','bear','sideways','unknown'):
        group=[t for t in trades if t['entry_regime']==regime]
        regime_stats[regime]={'trades':len(group),'net_pnl_initial_equity_pct':round(sum(t['net_pnl'] for t in group)*100,4),
                              'winning_trades':sum(t['net_pnl']>0 for t in group)}
    return {'return_pct':round((cash-1)*100,3),'max_drawdown_pct':round(max_dd*100,3),
            'completed_trades':len(trades),'orders':len(trades)*2,
            'win_rate_pct':round(100*sum(t['net_pnl']>0 for t in trades)/len(trades),2) if trades else None,
            'ledger_pnl_reconciles':abs(sum(t['net_pnl'] for t in trades)-(cash-1))<1e-7,
            'trades':trades,'regime_by_entry':regime_stats,'equity_curve':equity_curve}

def check(prices,start,end,hold,allocation):
    independent=replay(prices,start,end,hold,allocation)
    legacy=legacy_run(prices,start,end,'crypto',hold,allocation,.06)
    fields=('return_pct','max_drawdown_pct','completed_trades','orders','win_rate_pct')
    mismatches={k:{'independent':independent[k],'legacy':legacy[k]} for k in fields if independent[k]!=legacy[k]}
    return {'hold_days':hold,'allocation':allocation,'match':not mismatches,
            'mismatches':mismatches,'legacy':legacy,'independent':independent}

def main():
    report={'version':'3.5','mode':'research-only; no orders','approved_for_trading':False,
            'limitations':['Replays the existing signal logic; not independent signal verification.',
                           'Market regimes are classified at entry, not PnL apportioned across days.',
                           'Close-only fills; no intraday execution, liquidity or live slippage.',
                           'Historical selection bias remains; forward paper testing required.'],
            'results':[],'errors':[]}
    with requests.Session() as session:
        for symbol in ('BTC-USD','ETH-USD','SOL-USD'):
            try:
                candles,quality=fetch(session,symbol,86400,1825,datetime.now(timezone.utc))
                item={'symbol':symbol,'quality':quality,'approved_for_trading':False}
                if quality['status']=='PASS':
                    prices=[float(c['close']) for c in candles]
                    bounds=[int(len(prices)*f) for f in (.55,.70,.85,1)]
                    item['checks']=[check(prices,bounds[j],bounds[j+1],hold,allocation)
                                    for hold in (30,60) for allocation in (.25,.5) for j in range(3)]
                    item['all_reconciled']=all(c['match'] and c['independent']['ledger_pnl_reconciles'] for c in item['checks'])
                report['results'].append(item)
            except (ValueError,KeyError,TypeError,requests.RequestException) as exc:
                report['errors'].append({'symbol':symbol,'error':str(exc)})
    Path('independent_verification_v35.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return 0 if report['results'] and not report['errors'] and all(x.get('all_reconciled',False) for x in report['results']) else 1

if __name__=='__main__':
    raise SystemExit(main())
