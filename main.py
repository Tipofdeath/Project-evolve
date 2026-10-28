import os, time, logging
from datetime import datetime, timezone
from market import fetch_candles
from database import Database
from strategies import signal
from evolution import evaluate

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
DB=Database(os.getenv('EVOLVE_DB','evolve.sqlite3'))
POLL=int(os.getenv('POLL_SECONDS','60'))

def run_once():
    candles=fetch_candles()
    if len(candles)<35: raise RuntimeError('Not enough market candles')
    completed=candles[-2]  # most recent candle may still be forming
    timestamp,price=completed['time'],completed['close']
    if not DB.record_candle(timestamp,price):
        logging.info('No new completed candle')
        return
    for bot in DB.bots():
        if not bot['active']: continue
        action=signal(bot['strategy'],candles[:-1])
        DB.execute_paper_trade(bot,action,price,timestamp)
    evaluate(DB, timestamp)
    logging.info('Processed %s at %.4f; equity %.2f',datetime.fromtimestamp(timestamp,timezone.utc),price,DB.total_equity(price))

if __name__=='__main__':
    DB.seed()
    while True:
        try: run_once()
        except Exception: logging.exception('Polling failed; retrying')
        time.sleep(max(POLL,30))
