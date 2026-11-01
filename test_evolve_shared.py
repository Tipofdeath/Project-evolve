import unittest
from evolve_shared import metadata, LIVE_ORDERS_ENABLED
from database import Database
from evolve_paper_v46 import fresh, step

class IntegrationTests(unittest.TestCase):
    def test_release(self):
        self.assertFalse(LIVE_ORDERS_ENABLED)
        self.assertEqual(metadata('minute-auto')['shared_release'], metadata('daily-forward')['shared_release'])
    def test_database(self):
        db=Database(':memory:')
        db.seed()
        self.assertEqual(len(db.bots()),3)
        db.conn.close()
    def test_forward_idempotency(self):
        p=fresh('2026-10-31')
        candle={'time':'2026-11-01T00:00:00+00:00','open':100.,'low':99.,'close':101.}
        step(p,candle,{'signal':True},'original')
        self.assertGreater(p['qty'],0)
        previous=p.copy()
        step(p,candle,{'signal':True},'original')
        self.assertEqual(p,previous)

if __name__=='__main__': unittest.main()
