"""EVOLVE 2.3: adaptive, research-only strategy gate.
Usage: python evolve_backtest_v23.py [market_snapshot.json]
Uses earlier data for selection; evaluates only the selected policy on holdout.
No broker connections or orders.
"""
import json
import math
import statistics
import sys
from pathlib import Path

MIN_BARS = 300
WARMUP = 60
STRATEGIES = ("trend", "momentum", "breakout", "mean_reversion")
SIDE_COST = {"crypto": 0.0025, "forex": 0.0002, "gold": 0.0005}


def avg(values):
    return sum(values) / len(values)


def regime(prices, i):
    """Regime from data strictly before simulated execution bar i."""
    h = prices[:i]
    changes = [h[j] / h[j-1] - 1 for j in range(len(h)-19, len(h))]
    vol = statistics.pstdev(changes)
    drift = abs(avg(h[-10:]) / avg(h[-40:]) - 1)
    if vol > 0.035:
        return "high_volatility"
    if drift > max(0.004, 1.5 * vol):
        return "trending"
    return "ranging"


def wants_long(strategy, prices, i):
    h = prices[:i]
    if strategy == "trend":
        return avg(h[-10:]) > avg(h[-30:]) * 1.001
    if strategy == "momentum":
        return h[-1] > h[-13] * 1.015 and avg(h[-5:]) > avg(h[-20:])
    if strategy == "breakout":
        return h[-1] > max(h[-21:-1])
    if strategy == "mean_reversion":
        mu = avg(h[-20:])
        sd = statistics.pstdev(h[-20:])
        return sd > 0 and h[-1] < mu - 1.5 * sd
    return False


def backtest(prices, strategy, start, stop, cost, adaptive=False):
    cash, units, peak, dd, orders = 1.0, 0.0, 1.0, 0.0, 0
    for i in range(start, stop):
        price = prices[i]
        market_regime = regime(prices, i)
        allowed = (market_regime != "high_volatility" and
                   (not adaptive or
                    (strategy in ("trend", "momentum", "breakout") and market_regime == "trending") or
                    (strategy == "mean_reversion" and market_regime == "ranging")))
        target = allowed and wants_long(strategy, prices, i)
        if target and units == 0:
            units = cash * (1-cost) / price
            cash = 0
            orders += 1
        elif not target and units > 0:
            cash = units * price * (1-cost)
            units = 0
            orders += 1
        equity = cash + units * price
        peak = max(peak, equity)
        dd = max(dd, (peak-equity)/peak)
    if units:
        cash = units * prices[stop-1] * (1-cost)
        orders += 1
        dd = max(dd, (peak-cash)/peak)
    return {"return_pct": round((cash-1)*100, 3),
            "max_drawdown_pct": round(dd*100, 3), "orders": orders}


def evaluate(market):
    result = {"symbol": market.get("symbol"), "market": market.get("market")}
    try:
        candles = market["candles"]
        times = [str(c["time"]) for c in candles]
        prices = [float(c["close"]) for c in candles]
        if not prices or any(not math.isfinite(x) or x <= 0 for x in prices):
            raise ValueError("invalid prices")
        if times != sorted(times) or len(set(times)) != len(times):
            raise ValueError("timestamps must be unique and increasing")
    except (KeyError, ValueError, TypeError) as exc:
        return dict(result, status="INVALID_DATA", reason=str(exc))
    n = len(prices)
    result["candles"] = n
    if n < MIN_BARS:
        return dict(result, status="INSUFFICIENT_HISTORY", required=MIN_BARS)
    split = int(n * 0.7)
    cost = SIDE_COST.get(result["market"], 0.0025)
    training = {s: backtest(prices, s, WARMUP, split, cost, adaptive=True)
                for s in STRATEGIES}
    # A strategy must have meaningful trading activity, positive training return
    # and limited training drawdown. Otherwise choose cash / no trade.
    eligible = [s for s in STRATEGIES if training[s]["orders"] >= 4
                and training[s]["return_pct"] > 1.0
                and training[s]["max_drawdown_pct"] < 8.0]
    chosen = max(eligible, key=lambda s:
                 training[s]["return_pct"] - training[s]["max_drawdown_pct"]) if eligible else None
    holdout = (backtest(prices, chosen, split, n, cost, adaptive=True)
               if chosen else {"return_pct": 0.0, "max_drawdown_pct": 0.0, "orders": 0})
    return dict(result, status="EXPERIMENTAL_ONLY", selected_strategy=chosen or "NO_TRADE",
                latest_regime=regime(prices, n), training_results=training,
                holdout=holdout, training_bars=split-WARMUP, holdout_bars=n-split,
                holdout_buy_hold_pct=round((prices[-1]/prices[split]-1)*100, 3),
                assumed_cost_per_side_pct=cost*100,
                warning="Research only. One split, close-only execution; no verified spreads, financing, or broker execution.")


def main():
    path = Path(sys.argv[1]) if len(sys.argv)>1 else Path("market_snapshot.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    results = [evaluate(m) for m in data["markets"]]
    Path("backtest_report_v23.json").write_text(
        json.dumps({"version":"2.3", "mode":"research-only; no orders",
                    "source_generated_at":data.get("generated_at"), "results":results}, indent=2),
        encoding="utf-8")
    for r in results:
        if r["status"] == "EXPERIMENTAL_ONLY":
            print(f'{r["symbol"]}: {r["selected_strategy"]} | regime {r["latest_regime"]} | holdout {r["holdout"]["return_pct"]:+.3f}% | orders {r["holdout"]["orders"]}')
        else:
            print(f'{r["symbol"]}: {r["status"]}')
    print("Saved backtest_report_v23.json")


if __name__ == "__main__":
    main()
