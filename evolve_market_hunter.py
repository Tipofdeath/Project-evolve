"""Read-only rotating multi-market scan; no live trades."""
import json
from datetime import datetime,timezone
from pathlib import Path
import requests
from evolve_market_structure_v53 import fetch,aggregate_4h,analyze

def run():
    now=datetime.now(timezone.utc)
    state_file=Path("market_hunter_state.json")
    state=json.loads(state_file.read_text()) if state_file.exists() else {"cursor":0}
    with requests.Session() as s:
        response=s.get("https://api.exchange.coinbase.com/products",timeout=30)
        response.raise_for_status()
        universe=sorted({p["id"] for p in response.json()
            if p.get("quote_currency")=="USD" and p.get("status")=="online"
            and not p.get("trading_disabled") and p.get("id","").endswith("-USD")
            and p.get("base_currency") not in ("USDC","USDT","DAI")})
        if not universe:raise ValueError("no eligible markets")
        start=int(state["cursor"])%len(universe)
        selected=[universe[(start+i)%len(universe)] for i in range(min(12,len(universe)))]
        results=[];errors=[]
        for sym in selected:
            try:
                bars={tf:fetch(s,sym,sec,int(now.timestamp()))
                      for tf,sec in (("15m",900),("1h",3600),("1d",86400))}
                bars["4h"]=aggregate_4h(bars["1h"])
                f={tf:analyze(b) for tf,b in bars.items()}
                labels={tf:f[tf]["structure"] for tf in ("15m","1h","4h","1d")}
                eligible=(labels["1d"]=="bullish" or labels["4h"]=="bullish") and all(
                    labels[tf]!="bearish" for tf in labels)
                score=sum(v=="bullish" for v in labels.values())
                results.append({"symbol":sym,"research_candidate":eligible and score>=2,
                    "score":score,"structure":labels,"last_price":f["15m"]["close"]})
            except (ValueError,TypeError,KeyError,IndexError,requests.RequestException) as e:
                errors.append({"symbol":sym,"error":str(e)[:150]})
    results.sort(key=lambda x:(not x["research_candidate"],-x["score"]))
    Path("market_hunter_report.json").write_text(json.dumps({
        "version":"market-hunter-research-1","evaluated_at":now.isoformat(),
        "paper_only":True,"approved_for_trading":False,"live_orders_enabled":False,
        "universe_size":len(universe),"scanned":selected,"timeframes":["15m","1h","4h","1d"],
        "ranked_results":results,"errors":errors,
        "limitations":["Candidates are not proven profitable","No real trades",
                       "Incomplete or discontinuous candles rejected",
                       "No order-book or spread checks"]},indent=2)+"\n")
    state_file.write_text(json.dumps({"cursor":(start+len(selected))%len(universe)})+"\n")
if __name__=="__main__":run()
