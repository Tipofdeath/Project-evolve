"""Offline regression checks for shadow-only v5.4 consensus."""
import unittest
from datetime import datetime, timezone, timedelta
from evolve_structure_consensus_v54 import evaluate, AUTO_MARKETS

NOW=datetime(2026,11,1,16,0,tzinfo=timezone.utc)
SECONDS={"15m":900,"1h":3600,"4h":14400,"1d":86400}
def fixture():
    c={"evaluated_at":NOW.isoformat(),"approved_for_trading":False,"errors":[],
       "results":[{"symbol":s,"paper_entry_candidate":True} for s in AUTO_MARKETS]}
    markets={}
    for sym in AUTO_MARKETS:
        markets[sym]={}
        for tf,seconds in SECONDS.items():
            end=int(NOW.timestamp())//seconds*seconds
            markets[sym][tf]={"asof_candle_open_utc":datetime.fromtimestamp(end-seconds,timezone.utc).isoformat(),
                "structure":"bullish","close":100.0,"recent_swing_low":{"price":90.0}}
    s={"evaluated_at":NOW.isoformat(),"approved_for_trading":False,"errors":[],"markets":markets}
    return c,s

class StructureShadowTests(unittest.TestCase):
    def test_bullish_alignment(self):
        c,s=fixture()
        self.assertTrue(all(x["structure_filtered_candidate"] for x in evaluate(c,s,NOW)))
    def test_bearish_daily_rejected(self):
        c,s=fixture();s["markets"][AUTO_MARKETS[0]]["1d"]["structure"]="bearish"
        self.assertFalse(evaluate(c,s,NOW)[0]["structure_filtered_candidate"])
    def test_broken_swing_rejected(self):
        c,s=fixture();s["markets"][AUTO_MARKETS[0]]["15m"]["recent_swing_low"]["price"]=110
        self.assertIn("broken_swing_low_15m",evaluate(c,s,NOW)[0]["structure_reasons"])
    def test_stale_data_rejected(self):
        c,s=fixture();s["markets"][AUTO_MARKETS[0]]["15m"]["asof_candle_open_utc"]=(NOW-timedelta(hours=5)).isoformat()
        self.assertFalse(evaluate(c,s,NOW)[0]["structure_filtered_candidate"])
    def test_upstream_errors_fail_closed(self):
        c,s=fixture();s["errors"]=["missing candles"]
        with self.assertRaises(ValueError):evaluate(c,s,NOW)
    def test_missing_market_fails_closed(self):
        c,s=fixture();del s["markets"][AUTO_MARKETS[0]]
        with self.assertRaises(ValueError):evaluate(c,s,NOW)

if __name__=="__main__":unittest.main()
