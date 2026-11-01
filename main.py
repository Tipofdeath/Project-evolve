import os, time, logging
from datetime import datetime, timezone
from market import fetch_candles
from database import Database
from strategies import signal
from evolution import evaluate
from evolve_shared import metadata, AUTO_MARKETS

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logging.info('EVOLVE integration: %s',metadata('minute-auto'))
DB=Database(os.getenv('EVOLVE_DB','evolve.sqlite3'))
POLL=int(os.getenv('POLL_SECONDS','60'))

def run_once():
    for symbol in AUTO_MARKETS:
        try:
            candles=fetch_candles(symbol)
            if len(candles)<35: raise RuntimeError('Not enough market candles')
            completed=candles[-2]  # exclude still-forming minute
            timestamp,price=completed['time'],completed['close']
            if not DB.record_candle(timestamp,price,symbol):
                logging.info('%s: no new completed candle',symbol)
                continue
            for bot in DB.bots(symbol):
                if not bot['active']: continue
                action=signal(bot['strategy'],candles[:-1])
                DB.execute_paper_trade(bot,action,price,timestamp)
            evaluate(DB,timestamp,symbol)
            logging.info('%s %s price %.4f; paper equity %.2f',
                         symbol,datetime.fromtimestamp(timestamp,timezone.utc),
                         price,DB.total_equity(price,symbol))
        except Exception:
            logging.exception('%s paper scan failed; other markets continue',symbol)

if __name__=='__main__':
    DB.seed()
    while True:
        try: run_once()
        except Exception: logging.exception('Polling failed; retrying')
        time.sleep(max(POLL,30))
