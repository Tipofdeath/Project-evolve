"""EVOLVE 5.5 prospective, independent shadow comparison; never places orders."""
import json,math
from pathlib import Path
from datetime import datetime,timezone
import requests
from evolve_shared import AUTO_MARKETS,FORWARD_FEE,FORWARD_SLIPPAGE

STATE=Path("shadow_performance_state_v55.json")
REPORT=Path("shadow_performance_report_v55.json")
VERSION="5.5-shadow-performance"
COST=(1-FORWARD_FEE)*(1-FORWARD_SLIPPAGE)
STOP=.025
HOLD=96*900

def initial():
    return {"version":VERSION,"last_bar":{},"strategies":{
        name:{"cash":1.,"positions":{},"pending":{},"trades":[],"peak":1.,"max_drawdown_pct":0.}
        for name in ("baseline","structure")},"skipped_intervals":0,"observations":0}

def fetch(session,sym,now):
    boundary=int(now.timestamp())//900*900
    response=session.get("https://api.exchange.coinbase.com/products/"+sym+"/candles",
        params={"granularity":900},headers={"User-Agent":"EVOLVE-shadow/5.5"},timeout=30)
    response.raise_for_status()
    rows=response.json()
    if not isinstance(rows,list):raise ValueError("invalid candle response")
    valid={}
    for x in rows:
        if not isinstance(x,list) or len(x)<6:continue
        t=int(x[0])
        if t>=boundary or t%900:continue
        low,high,op,close=map(float,x[1:5])
        if not all(math.isfinite(v) and v>0 for v in (low,high,op,close)):continue
        if not low<=min(op,close)<=max(op,close)<=high:continue
        valid[t]={"t":t,"o":op,"h":high,"l":low,"c":close}
    if not valid:raise ValueError("no completed candles")
    return [valid[t] for t in sorted(valid)]

def read_signals(now):
    a=json.loads(Path("structure_consensus_report_v54.json").read_text())
    b=json.loads(Path("consensus_report_v50.json").read_text())
    if a.get("errors") or b.get("errors"):raise ValueError("upstream signal errors")
    if a.get("approved_for_trading") is not False or b.get("approved_for_trading") is not False:
        raise ValueError("invalid research flags")
    if a.get("signals_used_for_execution") is not False:raise ValueError("shadow flag missing")
    for report in (a,b):
        dt=datetime.fromisoformat(report["evaluated_at"])
        if dt.tzinfo is None or not 0<=(now-dt).total_seconds()<=3600:
            raise ValueError("stale signal report")
    x={v["symbol"]:v for v in a["results"]}
    y={v["symbol"]:v for v in b["results"]}
    if set(x)!=set(AUTO_MARKETS) or set(y)!=set(AUTO_MARKETS):
        raise ValueError("missing signals")
    if any((x[s].get("baseline_candidate") is True)!=(y[s].get("paper_entry_candidate") is True) for s in AUTO_MARKETS):
        raise ValueError("baseline mismatch")
    return {"baseline":{s:y[s].get("paper_entry_candidate") is True for s in AUTO_MARKETS},
        "structure":{s:x[s].get("structure_filtered_candidate") is True for s in AUTO_MARKETS},
        "at":max(datetime.fromisoformat(a["evaluated_at"]).timestamp(),
                 datetime.fromisoformat(b["evaluated_at"]).timestamp())}

def metrics(p,bars):
    equity=p["cash"]+sum(pos["qty"]*bars[s]["c"] for s,pos in p["positions"].items())
    low=p["cash"]+sum(pos["qty"]*bars[s]["l"] for s,pos in p["positions"].items())
    p["max_drawdown_pct"]=max(p["max_drawdown_pct"],100*(p["peak"]-min(equity,low))/p["peak"])
    p["peak"]=max(p["peak"],equity)
    wins=sum(t["pnl"]>0 for t in p["trades"])
    return {"equity":round(equity,8),"return_pct":round(100*(equity-1),4),
        "max_drawdown_pct":round(p["max_drawdown_pct"],4),"closed_trades":len(p["trades"]),
        "wins":wins,"win_rate_pct":round(100*wins/len(p["trades"]),2) if p["trades"] else None,
        "average_trade_pnl":round(sum(t["pnl"] for t in p["trades"])/len(p["trades"]),8) if p["trades"] else None,
        "open_positions":sorted(p["positions"]),"pending_signals":sorted(p["pending"])}

def advance(p,bars,signals,at):
    for sym in AUTO_MARKETS:
        b=bars[sym];pos=p["positions"].get(sym)
        if pos:
            exit_price=None;reason=None
            if b["o"]<=pos["stop"]:exit_price=b["o"]*.995;reason="gap_stop"
            elif b["l"]<=pos["stop"]:exit_price=pos["stop"]*.995;reason="stop_touch"
            elif b["t"]-pos["entry_t"]>=HOLD:exit_price=b["o"];reason="max_hold"
            if exit_price is not None:
                proceeds=pos["qty"]*exit_price*COST
                p["cash"]+=proceeds
                p["trades"].append({"symbol":sym,"entry_t":pos["entry_t"],"exit_t":b["t"],
                    "reason":reason,"pnl":round(proceeds-pos["basis"],9)})
                del p["positions"][sym]
    for sym in AUTO_MARKETS:
        b=bars[sym];signal_at=p["pending"].get(sym)
        if signal_at is None:continue
        if b["t"]<signal_at:continue
        del p["pending"][sym]
        if b["t"]-signal_at>3600 or sym in p["positions"]:continue
        equity=p["cash"]+sum(pos["qty"]*bars[s]["o"] for s,pos in p["positions"].items())
        exposure=sum(pos["qty"]*bars[s]["o"] for s,pos in p["positions"].items())
        budget=min(p["cash"]*.10,max(0.,.30*equity-exposure))
        if budget<=0:continue
        p["cash"]-=budget
        qty=budget*COST/b["o"]
        stop=b["o"]*(1-STOP)
        p["positions"][sym]={"qty":qty,"basis":budget,"entry_t":b["t"],"stop":stop}
        if b["l"]<=stop:
            proceeds=qty*stop*.995*COST
            p["cash"]+=proceeds
            p["trades"].append({"symbol":sym,"entry_t":b["t"],"exit_t":b["t"],
                "reason":"entry_bar_stop_assumed","pnl":round(proceeds-budget,9)})
            del p["positions"][sym]
    for sym in AUTO_MARKETS:
        if signals[sym] and sym not in p["positions"] and sym not in p["pending"]:
            p["pending"][sym]=at
    return metrics(p,bars)

def process(state,history,signals):
    if state.get("version")!=VERSION:raise ValueError("incompatible state")
    if set(history)!=set(AUTO_MARKETS):raise ValueError("missing market candles")
    bars={s:history[s][-1] for s in AUTO_MARKETS}
    times={s:bars[s]["t"] for s in AUTO_MARKETS}
    if not state["last_bar"]:
        state["last_bar"]=times
        for name,p in state["strategies"].items():
            for sym in AUTO_MARKETS:
                if signals[name][sym]:p["pending"][sym]=signals["at"]
        return {"initialized":True}
    deltas={s:times[s]-state["last_bar"][s] for s in AUTO_MARKETS}
    if all(v==0 for v in deltas.values()):
        return {"no_new_candle":True}
    if any(v<0 or v%900 for v in deltas.values()):
        raise ValueError("invalid candle chronology")
    if any(v==0 for v in deltas.values()):
        raise ValueError("inconsistent candle advancement")
    # Never backfill trades using signals only known now.
    if any(v>900 for v in deltas.values()):
        if any(p["positions"] or p["pending"] for p in state["strategies"].values()):
            raise ValueError("missing candles with exposure or pending signal; manual review")
        state["skipped_intervals"]+=sum(v//900-1 for v in deltas.values())
        state["last_bar"]=times
        return {"skipped_unobserved_intervals":True,
            "skipped_candles":{s:int(v//900-1) for s,v in deltas.items()}}
    # All prices must have exactly one new bar; process both strategies identically.
    result={name:advance(p,bars,signals[name],signals["at"])
        for name,p in state["strategies"].items()}
    state["last_bar"]=times
    state["observations"]+=1
    return {"comparison":result}

def run():
    now=datetime.now(timezone.utc)
    state=json.loads(STATE.read_text()) if STATE.exists() else initial()
    signals=read_signals(now)
    with requests.Session() as session:
        history={s:fetch(session,s,now) for s in AUTO_MARKETS}
    result=process(state,history,signals)
    # Publish both strategies' current equity, even on duplicate/skip cycles.
    bars={s:history[s][-1] for s in AUTO_MARKETS}
    result["strategies"]={name:metrics(p,bars) for name,p in state["strategies"].items()}
    result["observations"]=state["observations"]
    result["skipped_intervals"]=state["skipped_intervals"]
    STATE.write_text(json.dumps(state,indent=2)+"\n")
    REPORT.write_text(json.dumps({"version":VERSION,"evaluated_at":now.isoformat(),
        "paper_only":True,"approved_for_trading":False,"live_orders_enabled":False,
        "results":result,"errors":[],"limitations":[
            "Prospective signals only; no historical entry backfills",
            "Missed intervals with positions or pending signals fail closed",
            "OHLC stop fills and slippage are approximations",
            "Persistent artifact state is essential; no profitability validation yet"]},indent=2)+"\n")
    return 0

if __name__=="__main__":raise SystemExit(run())
