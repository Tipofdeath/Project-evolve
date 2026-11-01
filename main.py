"""EVOLVE daily paper entrypoint (1D UTC candles, BTC/ETH/SOL).
Legacy minute-trading SQLite is intentionally left untouched.
The canonical daily signal and execution rules live in v45/v46.
"""
import logging
from evolve_shared import metadata
from evolve_forward_v45 import run as update_signals
from evolve_paper_v46 import run as update_paper
from evolve_auto_dashboard_v47 import build as update_dashboard

logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')

def run_once():
    logging.info('Starting %s',metadata('daily-auto'))
    if update_signals()!=0:
        raise RuntimeError('Daily signal quality failed; paper execution skipped')
    if update_paper()!=0:
        raise RuntimeError('Daily paper execution failed; dashboard skipped')
    update_dashboard()
    logging.info('Daily research-only paper snapshot generated')
    return 0

if __name__=='__main__':
    raise SystemExit(run_once())
