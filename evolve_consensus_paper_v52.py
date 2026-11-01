"""EVOLVE 5.2 isolated, prospective paper execution for consensus candidates.
No exchange credentials, wallets, or live orders. No retroactive fills.
"""
import json,math
from pathlib import Path
from datetime import datetime,timezone
import requests
from evolve_shared import AUTO_MARKETS,metadata,FORWARD_FEE,FORWARD_SLIPPAGE

STATE=Path('consensus_paper_state_v52.json')
REPORT=Path('consensus_paper_report_v52.json')
VERSION='5.2-consensus-paper'
COST=(1-FORWARD_FEE)*(1-FORWARD_SLIPPAGE)
MAX_EXPOSURE=.30
ALLOCATION=.10
STOP=.025
MAX_HOLD=96*900

def new_state():
    return {'version':VERSION,'cash':1.,'positions':{},'trades':[],
            'last_bar':{},'pending':{},'peak_equity':1.,'max_drawdown_pct':0.}

def candle(session,symbol,now):
    boundary=int(now.timestamp())//900*900
    response=session.get('https://api.exchange.coinbase.com/products/'+symbol+'/candles',
        params={'granularity':900},headers={'User-Agent':'EVOLVE-consensus-paper/5.2'},timeout=30)
    response.raise_for_status()
    rows=response.json()
    valid=[]
    if not isinstance(rows,list):raise ValueError('invalid candle response')
    for row in rows:
        if not isinstance(row,list) or len(row)<6:continue
        t=int(row[0])
        if t>=boundary or t%900:continue
        lo,hi,op,cl=map(float,row[1:5])
        if not all(math.isfinite(x) and x>0 for x in (lo,hi,op,cl)):continue
        if not lo<=min(op,cl)<=max(op,cl)<=hi:continue
        valid.append({'t':t,'o':op,'h':hi,'l':lo,'c':cl})
    if not valid:raise ValueError('no completed candle')
    return max(valid,key=lambda x:x['t'])

def apply(state,bars,consensus,now):
    if state.get('version')!=VERSION:raise ValueError('wrong state version')
    if consensus.get('errors') or consensus.get('approved_for_trading') is not False:
        raise ValueError('invalid consensus report')
    at=datetime.fromisoformat(consensus['evaluated_at'])
    if at.tzinfo is None or not 0<=(now-at).total_seconds()<=3600:
        raise ValueError('stale consensus')
    candidates={x['symbol']:x for x in consensus['results']}
    pending=state.setdefault('pending',{})
    if set(candidates)!=set(AUTO_MARKETS):raise ValueError('missing consensus market')
    # GitHub may run before Coinbase publishes the next completed candle.
    # An unchanged candle is a harmless no-op, not a missing candle.
    deltas={sym:bars[sym]['t']-state['last_bar'][sym] for sym in AUTO_MARKETS}
    if all(delta==0 for delta in deltas.values()):
        equity=state['cash']+sum(p['qty']*bars[s]['c'] for s,p in state['positions'].items())
        return {'equity':round(equity,8),'return_pct':round((equity-1)*100,4),
            'max_drawdown_pct':round(state['max_drawdown_pct'],4),
            'open_positions':sorted(state['positions']),
            'closed_trades':len(state['trades']),'cash':round(state['cash'],8),
            'no_new_candle':True}
    # Never skip a missing candle or advance only some markets: no invented fills.
    for sym,delta in deltas.items():
        if delta!=900:
            raise ValueError('missing or inconsistent 15m candles for '+sym)
    # Position exits happen before entries. Stop fills conservatively include slippage.
    for sym in AUTO_MARKETS:
        b=bars[sym];pos=state['positions'].get(sym)
        if pos:
            stop=pos['stop'];exit_price=None;reason=None
            if b['o']<=stop:exit_price=b['o']*.995;reason='gap_stop'
            elif b['l']<=stop:exit_price=stop*.995;reason='stop_touch'
            elif b['t']-pos['entry_t']>=MAX_HOLD:exit_price=b['o'];reason='max_hold'
            if exit_price is not None:
                proceeds=pos['qty']*exit_price*COST
                state['cash']+=proceeds
                state['trades'].append({'symbol':sym,'entry_t':pos['entry_t'],
                    'exit_t':b['t'],'reason':reason,'pnl':round(proceeds-pos['basis'],9)})
                del state['positions'][sym]
    for sym in AUTO_MARKETS:
        b=bars[sym];signal=pending.get(sym)
        if signal is None:continue
        signal_at=signal['at']
        if b['t']<signal_at:continue
        del pending[sym]
        candidate=signal['candidate']
        # Candidate is generated after its input candles: enter only a later bar.
        # Require at least 3/4 confirmation and a genuine 15m trigger.
        if not (candidate.get('paper_entry_candidate') is True and
                isinstance(candidate.get('confirmation_score'),int) and
                candidate['confirmation_score']>=3):continue
        if sym in state['positions']:continue
        if b['t']-signal_at>3600:continue
        equity=state['cash']+sum(p['qty']*bars[s]['o'] for s,p in state['positions'].items())
        exposure=sum(p['qty']*bars[s]['o'] for s,p in state['positions'].items())
        budget=min(state['cash']*.10,max(0,MAX_EXPOSURE*equity-exposure))
        if budget<=0:continue
        state['cash']-=budget
        qty=budget*COST/b['o']
        stop=b['o']*(1-STOP)
        state['positions'][sym]={'qty':qty,'basis':budget,'entry_t':b['t'],'stop':stop}
        if b['l']<=stop:
            proceeds=qty*stop*.995*COST
            state['cash']+=proceeds
            state['trades'].append({'symbol':sym,'entry_t':b['t'],
                'exit_t':b['t'],'reason':'entry_bar_stop_assumed',
                'pnl':round(proceeds-budget,9)})
            del state['positions'][sym]
    for sym in AUTO_MARKETS:
        candidate=candidates[sym]
        if candidate.get('paper_entry_candidate') is True and sym not in state['positions'] and sym not in pending:
            pending[sym]={'at':at.timestamp(),'candidate':candidate}
        state['last_bar'][sym]=bars[sym]['t']
    equity=state['cash']+sum(p['qty']*bars[s]['c'] for s,p in state['positions'].items())
    low_equity=state['cash']+sum(p['qty']*bars[s]['l'] for s,p in state['positions'].items())
    state['max_drawdown_pct']=max(state['max_drawdown_pct'],
        100*(state['peak_equity']-min(equity,low_equity))/state['peak_equity'])
    state['peak_equity']=max(state['peak_equity'],equity)
    return {'equity':round(equity,8),'return_pct':round((equity-1)*100,4),
        'max_drawdown_pct':round(state['max_drawdown_pct'],4),
        'open_positions':sorted(state['positions']),
        'closed_trades':len(state['trades']),'cash':round(state['cash'],8)}

def run():
    now=datetime.now(timezone.utc)
    state=json.loads(STATE.read_text()) if STATE.exists() else new_state()
    consensus=json.loads(Path('consensus_report_v50.json').read_text())
    with requests.Session() as session:
        bars={sym:candle(session,sym,now) for sym in AUTO_MARKETS}
    # Initial observation only: no historical trades.
    if not state['last_bar']:
        state['last_bar']={sym:bars[sym]['t'] for sym in AUTO_MARKETS}
        at=datetime.fromisoformat(consensus['evaluated_at'])
        if at.tzinfo is None or not 0<=(now-at).total_seconds()<=3600:
            raise ValueError('stale consensus')
        if consensus.get('errors'):raise ValueError('consensus errors')
        state['pending']={x['symbol']:{'at':at.timestamp(),'candidate':x}
            for x in consensus['results'] if x.get('paper_entry_candidate') is True}
        result={'equity':1.,'return_pct':0.,'max_drawdown_pct':0.,
                'open_positions':[],'closed_trades':0,'cash':1.,'initialized':True}
    else:
        result=apply(state,bars,consensus,now)
    # Write state only on complete success; exceptions preserve the prior state.
    STATE.write_text(json.dumps(state,indent=2)+'\n')
    REPORT.write_text(json.dumps({'version':VERSION,'integration':metadata('consensus-paper-execution'),
        'paper_only':True,'approved_for_trading':False,
        'evaluated_at':now.isoformat(),'results':result,'errors':[],
        'limitations':['Prospective 15m OHLC paper fills only','Fees and slippage estimated',
          'Intrabar stop ordering approximated','No live orders or wallets',
          'Artifact state restoration required for continuity']},indent=2)+'\n')
    return 0
if __name__=='__main__':raise SystemExit(run())
