"""EVOLVE 5.3: read-only, multi-timeframe market structure research.
Confirmed Coinbase candles only. No orders, portfolio changes or lookahead.
"""
import json, math
from datetime import datetime, timezone
from pathlib import Path
import requests
from evolve_shared import AUTO_MARKETS

OUT=Path("market_structure_report_v53.json")
GRANULARITIES={"15m":900,"1h":3600,"1d":86400}

def fetch(session,symbol,seconds,now):
    cutoff=now//seconds*seconds
    response=session.get(f"https://api.exchange.coinbase.com/products/{symbol}/candles",
        params={"granularity":seconds},headers={"User-Agent":"EVOLVE-structure-paper/5.3"},timeout=30)
    response.raise_for_status()
    rows=response.json()
    if not isinstance(rows,list):raise ValueError("invalid candles")
    by_time={}
    for row in rows:
        if not isinstance(row,list) or len(row)<6:continue
        t=int(row[0])
        if t>=cutoff or t%seconds:continue
        lo,hi,op,cl=map(float,row[1:5])
        if not all(math.isfinite(v) and v>0 for v in (lo,hi,op,cl)):continue
        if not lo<=min(op,cl)<=max(op,cl)<=hi:continue
        by_time[t]={"t":t,"o":op,"h":hi,"l":lo,"c":cl}
    bars=[by_time[t] for t in sorted(by_time)]
    if len(bars)<40:raise ValueError("insufficient completed candles")
    if any(b["t"]-a["t"]!=seconds for a,b in zip(bars,bars[1:])):
        raise ValueError("discontinuous candles")
    return bars

def aggregate_4h(hourly):
    """Construct actual UTC-aligned four-hour candles from complete 1h candles."""
    groups={}
    for bar in hourly:
        t=bar["t"]//14400*14400
        groups.setdefault(t,[]).append(bar)
    result=[]
    for t in sorted(groups):
        group=groups[t]
        if [x["t"] for x in group]!=[t+i*3600 for i in range(4)]:
            continue
        result.append({"t":t,"o":group[0]["o"],"h":max(x["h"] for x in group),
            "l":min(x["l"] for x in group),"c":group[-1]["c"]})
    if len(result)<40 or any(b["t"]-a["t"]!=14400 for a,b in zip(result,result[1:])):
        raise ValueError("insufficient or discontinuous actual 4h candles")
    return result

def pivots(bars,side=3):
    highs=[];lows=[]
    # Right-hand confirmation: only bars at least side candles old can become pivots.
    for i in range(side,len(bars)-side):
        group=bars[i-side:i+side+1]
        if bars[i]["h"]==max(b["h"] for b in group) and sum(b["h"]==bars[i]["h"] for b in group)==1:
            highs.append({"t":bars[i]["t"],"price":bars[i]["h"],"confirmed_at":bars[i+side]["t"]})
        if bars[i]["l"]==min(b["l"] for b in group) and sum(b["l"]==bars[i]["l"] for b in group)==1:
            lows.append({"t":bars[i]["t"],"price":bars[i]["l"],"confirmed_at":bars[i+side]["t"]})
    return highs,lows

def analyze(bars):
    highs,lows=pivots(bars)
    close=bars[-1]["c"]
    high=highs[-1] if highs else None
    low=lows[-1] if lows else None
    structure="insufficient_confirmed_swings"
    if len(highs)>=2 and len(lows)>=2:
        hh=highs[-1]["price"]>highs[-2]["price"]
        hl=lows[-1]["price"]>lows[-2]["price"]
        lh=highs[-1]["price"]<highs[-2]["price"]
        ll=lows[-1]["price"]<lows[-2]["price"]
        structure="bullish" if hh and hl else "bearish" if lh and ll else "mixed_or_range"
    prev=bars[-2]
    bos_up=bool(high and prev["c"]<=high["price"]<close and high["confirmed_at"]<bars[-1]["t"])
    bos_down=bool(low and prev["c"]>=low["price"]>close and low["confirmed_at"]<bars[-1]["t"])
    sweep_high=bool(high and bars[-1]["h"]>high["price"] and close<high["price"])
    sweep_low=bool(low and bars[-1]["l"]<low["price"] and close>low["price"])
    # A CHoCH label requires an established opposing swing structure.
    choch_up=structure=="bearish" and bos_up
    choch_down=structure=="bullish" and bos_down
    # Three-candle displacement gap; zones are descriptive, not trade instructions.
    gaps=[]
    for i in range(2,len(bars)):
        a,b,c=bars[i-2:i+1]
        if c["l"]>a["h"]:gaps.append({"side":"bullish","low":a["h"],"high":c["l"],"at":c["t"]})
        if c["h"]<a["l"]:gaps.append({"side":"bearish","low":c["h"],"high":a["l"],"at":c["t"]})
    return {"asof_candle_open_utc":datetime.fromtimestamp(bars[-1]["t"],timezone.utc).isoformat(),
        "close":close,"structure":structure,
        "recent_swing_high":high,"recent_swing_low":low,
        "bos_up":bos_up,"bos_down":bos_down,"choch_up":choch_up,"choch_down":choch_down,
        "liquidity_sweep_high":sweep_high,"liquidity_sweep_low":sweep_low,
        "recent_fair_value_gaps":gaps[-5:],
        "support_reference":low["price"] if low else None,
        "resistance_reference":high["price"] if high else None}

def run():
    now=datetime.now(timezone.utc)
    results={};errors=[]
    with requests.Session() as session:
        for symbol in AUTO_MARKETS:
            results[symbol]={}
            for name,seconds in GRANULARITIES.items():
                try:
                    bars=fetch(session,symbol,seconds,int(now.timestamp()))
                    results[symbol][name]=analyze(bars)
                    if name=="1h":results[symbol]["4h"]=analyze(aggregate_4h(bars))
                except (ValueError,TypeError,KeyError,IndexError,requests.RequestException) as e:
                    errors.append({"symbol":symbol,"timeframe":name,"error":str(e)})
    OUT.write_text(json.dumps({"version":"5.3-market-structure-research",
        "evaluated_at":now.isoformat(),"paper_only":True,"approved_for_trading":False,
        "signals_used_for_execution":False,"markets":results,"errors":errors,
        "limitations":["Confirmed pivots lag by three candles","4h candles aggregated from complete UTC-aligned 1h candles","BOS and CHoCH are heuristic labels",
          "FVGs are historical gaps, not verified executable order blocks",
          "Coinbase API candle availability and gaps can limit coverage",
          "No backtested predictive accuracy or real-money execution"]},indent=2)+"\n")
    return 1 if errors else 0

if __name__=="__main__":raise SystemExit(run())
