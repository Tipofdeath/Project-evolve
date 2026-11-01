"""EVOLVE 3.9: causal SMC context research. Never places orders."""
import json
from datetime import datetime, timezone
from pathlib import Path
import requests
from evolve_execution_v36 import fetch_ohlc, SYMBOLS
from evolve_smc_v38 import detect

def _validate(candles):
    for c in candles:
        o,h,l,cl=[float(c[k]) for k in ('open','high','low','close')]
        if not (0<l<=min(o,cl)<=max(o,cl)<=h):
            raise ValueError('invalid OHLC')
    return candles

def completed_weekly(candles):
    """Only complete Monday-Sunday UTC weeks. Never use a partial current week."""
    groups={}
    for c in _validate(candles):
        stamp=datetime.fromisoformat(c['time'].replace('Z','+00:00'))
        if stamp.tzinfo is None:raise ValueError('timezone required')
        key=stamp.date().toordinal()-stamp.weekday()
        groups.setdefault(key,[]).append(c)
    weekly=[]
    for key,rows in sorted(groups.items()):
        if len(rows)!=7:continue
        days=sorted(datetime.fromisoformat(x['time'].replace('Z','+00:00')).date().toordinal() for x in rows)
        if days!=list(range(key,key+7)):continue
        rows=sorted(rows,key=lambda x:x['time'])
        weekly.append({'time':rows[-1]['time'],'open':float(rows[0]['open']),
                       'high':max(float(x['high']) for x in rows),
                       'low':min(float(x['low']) for x in rows),
                       'close':float(rows[-1]['close'])})
    return weekly

def context(candles):
    _validate(candles)
    d=detect(candles)
    weekly=completed_weekly(candles)
    w=detect(weekly) if len(weekly)>=6 else {'last_structure_direction':'unknown','events':[]}
    # Only the most recent confirmed high and low are used; never future extrema.
    hi=d['pivot_highs'][-1] if d['pivot_highs'] else None
    lo=d['pivot_lows'][-1] if d['pivot_lows'] else None
    price=float(candles[-1]['close'])
    zone='unavailable';mid=None
    if hi and lo and hi['price']>lo['price']:
        mid=(hi['price']+lo['price'])/2
        zone='premium' if price>mid else 'discount' if price<mid else 'equilibrium'
    # Heuristic candidate: last opposite-colored candle in 10 bars BEFORE
    # a close-confirmed break. No future candles used to choose its zone.
    blocks=[]
    for e in d['events']:
        if e['type'] not in ('BOS','CHoCH_candidate','structure_break'):continue
        i=e['bar'];direction=e['direction']
        for j in range(i-1,max(-1,i-11),-1):
            c=candles[j];o=float(c['open']);cl=float(c['close'])
            opposite=(cl<o) if direction=='bullish' else (cl>o)
            if opposite:
                blocks.append({'confirmed_at_bar':i,'source_bar':j,
                               'direction':direction,'low':float(c['low']),
                               'high':float(c['high']),'label':'order_block_candidate'})
                break
    # Confluence is descriptive only: no ranking, probability or trade signal.
    daily=d['last_structure_direction'];higher=w['last_structure_direction']
    agreement='aligned' if daily==higher and daily!='unknown' else 'conflicting' if daily!='unknown' and higher!='unknown' else 'unknown'
    return {'daily_structure':daily,'completed_weekly_candles':len(weekly),
            'weekly_structure':higher,'timeframe_agreement':agreement,
            'confirmed_range':{'high':hi,'low':lo,'midpoint':mid,'price_zone':zone},
            'order_block_candidate_count':len(blocks),
            'latest_order_block_candidates':blocks[-8:],
            'recent_daily_events':d['latest_events'][-6:],
            'latest_completed_week':weekly[-1]['time'] if weekly else None}

def main():
    report={'version':'3.9-smc-context','mode':'research-only; no orders',
            'approved_for_trading':False,
            'limitations':['Order blocks are heuristic candidates, not evidence of institutional activity.',
                           'Premium/discount range uses last confirmed swing high and low; no forecast.',
                           'Weekly structure uses only completed UTC Monday-Sunday candles.',
                           'No measured trading edge or live validation.'],
            'results':[],'errors':[]}
    with requests.Session() as session:
        for symbol in SYMBOLS:
            try:
                candles,q=fetch_ohlc(session,symbol)
                if q.get('status')!='PASS':raise ValueError('data quality failed')
                report['results'].append({'symbol':symbol,'quality':q,'context':context(candles)})
            except (requests.RequestException,ValueError,KeyError,TypeError) as exc:
                report['errors'].append({'symbol':symbol,'error':str(exc)})
    Path('smc_context_v39.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return 0 if len(report['results'])==len(SYMBOLS) and not report['errors'] else 1

if __name__=='__main__':raise SystemExit(main())
