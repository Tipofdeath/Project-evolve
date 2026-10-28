# Project EVOLVE 1.5 — paper trading

Python-only experimental SOL/USD trading colony using public Coinbase Exchange one-minute candles. **No real orders or wallets.** Three strategies each start with $10 virtual capital. Trades include 0.15% simulated fee and 0.10% slippage. Bot reproduction transfers $10 from the parent, subject to caps; no money is created. A bot deactivates at 30% peak-equity drawdown.

## Run

```bash
pip install -r requirements.txt
python main.py
```

Runs in the foreground, polling every 60 seconds. For 24/7 use, deploy as a persistent background process on a server with a **persistent disk**. SQLite state is saved in `evolve.sqlite3` (or `EVOLVE_DB`). This package does not yet include a web dashboard, authentication, automated deployment, or recovery from long outages. Missed candles are not back-traded. This is an experimental baseline, not a validated profitable strategy.
