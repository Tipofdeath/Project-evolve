"""EVOLVE 3.8: causal SMC feature research. No trades or order placement.

Working definitions adapted from the user's SMC study guide. A pivot at
index j is only confirmed after the right-side candles have CLOSED.
All event indices denote the confirmation/observation candle, never the pivot.
"""
import json
from pathlib import Path
import requests
from evolve_execution_v36 import fetch_ohlc, SYMBOLS

def detect(candles, left=2, right=2, equal_tolerance=.002):
    if left<1 or right<1 or not 0<=equal_tolerance<.1:
        raise ValueError('invalid settings')
    bars=[]
    for c in candles:
        o,h,l,cl=(float(c[k]) for k in ('open','high','low','close'))
        if not 0<l<=min(o,cl)<=max(o,cl)<=h:raise ValueError('invalid OHLC')
        bars.append({'open':o,'high':h,'low':l,'close':cl})
    highs=[];lows=[];events=[];trend='unknown'
    # On bar i, only inspect pivots j=i-right that are newly confirmable.
    for i in range(left+right,len(bars)):
        j=i-right
        window=bars[j-left:j+right+1]
        if all(bars[j]['high']>x['high'] for k,x in enumerate(window) if k!=left):
            highs.append({'pivot':j,'confirmed_at':i,'price':bars[j]['high']})
        if all(bars[j]['low']<x['low'] for k,x in enumerate(window) if k!=left):
            lows.append({'pivot':j,'confirmed_at':i,'price':bars[j]['low']})
        c=bars[i];prior=bars[i-1]
        # Only levels confirmed BEFORE this candle, and not already broken.
        for side,pivots,level_key,broken in (
            ('bullish',highs,'high','up'),('bearish',lows,'low','down')):
            eligible=[p for p in pivots if p['confirmed_at']<i]
            if not eligible:continue
            level=eligible[-1]['price']
            crossed=(prior['close']<=level<c['close']) if broken=='up' else (prior['close']>=level>c['close'])
            if crossed:
                kind='BOS' if trend==side else 'CHoCH_candidate' if trend not in ('unknown',side) else 'structure_break'
                events.append({'bar':i,'type':kind,'direction':side,'reference':level,'pivot':eligible[-1]['pivot']})
                trend=side
            # Wick crosses a known level but close returns inside it.
            swept=(c['high']>level and c['close']<level) if broken=='up' else (c['low']<level and c['close']>level)
            if swept:
                events.append({'bar':i,'type':'liquidity_sweep_candidate','direction':side,'reference':level})
        # FVG is known only at the close of its third candle.
        if i>=2:
            a=bars[i-2]
            if c['low']>a['high']:
                events.append({'bar':i,'type':'FVG','direction':'bullish','lower':a['high'],'upper':c['low']})
            if c['high']<a['low']:
                events.append({'bar':i,'type':'FVG','direction':'bearish','lower':c['high'],'upper':a['low']})
    return {'candles':len(bars),'pivot_highs':highs,'pivot_lows':lows,
            'events':events,'latest_events':events[-15:],
            'counts':{k:sum(e['type']==k for e in events) for k in
                      ('BOS','CHoCH_candidate','structure_break','liquidity_sweep_candidate','FVG')},
            'last_structure_direction':trend}

def main():
    report={'version':'3.8-smc-research','mode':'research-only; no orders',
            'approved_for_trading':False,
            'notes':['Daily Coinbase OHLC only; hourly scanner currently stores close-only candles.',
                     'Confirmed pivots require two future closed candles; no hindsight pivots.',
                     'SMC terms are operational chart labels, not proof of institutional orders.',
                     'No profitability comparison or forward validation yet.'],
            'results':[],'errors':[]}
    with requests.Session() as session:
        for symbol in SYMBOLS:
            try:
                candles,quality=fetch_ohlc(session,symbol)
                if quality.get('status')!='PASS':raise ValueError('data quality: '+str(quality))
                features=detect(candles)
                report['results'].append({'symbol':symbol,'quality':quality,
                    'counts':features['counts'],'last_structure_direction':features['last_structure_direction'],
                    'latest_events':features['latest_events'],
                    'pivot_high_count':len(features['pivot_highs']),
                    'pivot_low_count':len(features['pivot_lows'])})
            except (requests.RequestException,ValueError,KeyError,TypeError) as exc:
                report['errors'].append({'symbol':symbol,'error':str(exc)})
    Path('smc_features_v38.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return 0 if len(report['results'])==len(SYMBOLS) and not report['errors'] else 1

if __name__=='__main__':raise SystemExit(main())
