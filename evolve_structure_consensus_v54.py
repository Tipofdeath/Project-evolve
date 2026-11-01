"""EVOLVE 5.4: independent shadow comparison of structure-aware vs baseline consensus.
Research only. Does not alter v5.2 signals, paper state, or execute orders.
"""
import json
from pathlib import Path
from datetime import datetime, timezone
from evolve_shared import AUTO_MARKETS

OUT=Path("structure_consensus_report_v54.json")
MAX_AGE={"15m":3600,"1h":10800,"4h":28800,"1d":172800}
SECONDS={"15m":900,"1h":3600,"4h":14400,"1d":86400}

def parse(s):
    d=datetime.fromisoformat(s)
    if d.tzinfo is None:raise ValueError("naive timestamp")
    return d

def evaluate(consensus,structure,now):
    if consensus.get("errors") or structure.get("errors"):
        raise ValueError("upstream report errors")
    if consensus.get("approved_for_trading") is not False or structure.get("approved_for_trading") is not False:
        raise ValueError("upstream report approval flag invalid")
    if not 0<=(now-parse(consensus["evaluated_at"])).total_seconds()<=3600:
        raise ValueError("stale consensus report")
    if not 0<=(now-parse(structure["evaluated_at"])).total_seconds()<=3600:
        raise ValueError("stale structure report")
    baseline={x["symbol"]:x for x in consensus["results"]}
    if set(baseline)!=set(AUTO_MARKETS) or set(structure["markets"])!=set(AUTO_MARKETS):
        raise ValueError("missing or unexpected markets")
    output=[]
    for sym in AUTO_MARKETS:
        frames=structure["markets"][sym]
        reasons=[]
        if set(frames)!=set(MAX_AGE):
            reasons.append("missing_timeframes")
        else:
            for tf in MAX_AGE:
                item=frames[tf]
                # Candle opening timestamp is not the time at which it becomes known.
                completed_at=parse(item["asof_candle_open_utc"]).timestamp()+SECONDS[tf]
                age=now.timestamp()-completed_at
                if age<0 or age>MAX_AGE[tf]:
                    reasons.append("stale_or_future_"+tf)
                if item.get("structure") not in ("bullish","bearish","mixed_or_range","insufficient_confirmed_swings"):
                    reasons.append("invalid_structure_"+tf)
            day=frames["1d"]["structure"];four=frames["4h"]["structure"]
            hour=frames["1h"]["structure"];fifteen=frames["15m"]["structure"]
            if day=="bearish" or four=="bearish":reasons.append("higher_timeframe_bearish")
            if day!="bullish" and four!="bullish":reasons.append("no_bullish_higher_timeframe")
            if hour=="bearish" or fifteen=="bearish":reasons.append("lower_timeframe_bearish")
            if frames["15m"].get("choch_down") or frames["1h"].get("choch_down"):
                reasons.append("bearish_character_change")
            price=frames["15m"]["close"]
            if not isinstance(price,(int,float)) or price<=0:reasons.append("invalid_price")
            for tf in ("15m","1h"):
                swing=frames[tf].get("recent_swing_low")
                if swing and price<swing["price"]:
                    reasons.append("broken_swing_low_"+tf)
        base=baseline[sym].get("paper_entry_candidate") is True
        if not base:reasons.append("baseline_not_qualified")
        output.append({"symbol":sym,"baseline_candidate":base,
            "structure_filtered_candidate":base and not reasons,
            "structure_reasons":reasons,
            "structure_labels":{tf:frames[tf]["structure"] for tf in MAX_AGE if tf in frames}})
    return output

def run():
    now=datetime.now(timezone.utc)
    report={"version":"5.4-structure-shadow","evaluated_at":now.isoformat(),
        "paper_only":True,"approved_for_trading":False,
        "signals_used_for_execution":False,"results":[],"errors":[],
        "limitations":["Shadow research only; baseline paper executor unchanged",
            "Long-only conservative directional filter; no short orders",
            "Historical swing references are not guaranteed support",
            "Fair value gaps and order blocks are not used as filters",
            "No evidence yet that structure filtering improves returns"]}
    try:
        consensus=json.loads(Path("consensus_report_v50.json").read_text())
        structure=json.loads(Path("market_structure_report_v53.json").read_text())
        report["results"]=evaluate(consensus,structure,now)
    except (OSError,ValueError,KeyError,TypeError,IndexError,ZeroDivisionError) as e:
        report["errors"]=[str(e)]
    OUT.write_text(json.dumps(report,indent=2)+"\n")
    return 1 if report["errors"] else 0

if __name__=="__main__":raise SystemExit(run())
