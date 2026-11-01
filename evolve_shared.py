"""Shared, research-only EVOLVE release contract for both paper engines.
Increment RELEASE when a coordinated change is deployed to both engines.
"""
RELEASE = '4.7-shared'
LIVE_ORDERS_ENABLED = False
PAPER_ONLY = True
AUTO_STRATEGIES = ('trend','rsi','breakout')
FORWARD_STRATEGIES = ('original','breakout')
AUTO_MARKETS = ('BTC-USD','ETH-USD','SOL-USD')
AUTO_MARKET = 'SOL-USD'  # legacy SOL migration compatibility
FORWARD_MARKETS = ('BTC-USD','ETH-USD','SOL-USD')
# Each engine retains its previously declared execution assumptions;
# never silently equate minute-based and daily-based strategies.
AUTO_FEE = .0015
AUTO_SLIPPAGE = .001
FORWARD_FEE = .0025
FORWARD_SLIPPAGE = .001
def metadata(engine):
    return {'shared_release':RELEASE,'engine':engine,
            'paper_only':PAPER_ONLY,'live_orders_enabled':LIVE_ORDERS_ENABLED}
