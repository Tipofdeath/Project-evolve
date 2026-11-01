import sqlite3

from evolve_shared import AUTO_FEE as FEE, AUTO_SLIPPAGE as SLIP
class Database:
    def __init__(self,path):
        self.conn=sqlite3.connect(path)
        self.conn.row_factory=sqlite3.Row
        self.conn.executescript('''CREATE TABLE IF NOT EXISTS bots(id INTEGER PRIMARY KEY, parent INTEGER, generation INTEGER NOT NULL DEFAULT 0, strategy TEXT NOT NULL, cash REAL NOT NULL, sol REAL NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1, peak REAL NOT NULL DEFAULT 10, entry REAL, closed_trades INTEGER NOT NULL DEFAULT 0, wins INTEGER NOT NULL DEFAULT 0, realized REAL NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS candles(time INTEGER PRIMARY KEY, close REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS trades(id INTEGER PRIMARY KEY, bot_id INTEGER, time INTEGER, side TEXT, price REAL, quantity REAL, fee REAL, pnl REAL);
        CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, time INTEGER, event TEXT);''')
        self.conn.commit()
    def seed(self):
        if self.conn.execute('SELECT COUNT(*) FROM bots').fetchone()[0]==0:
            self.conn.executemany('INSERT INTO bots(strategy,cash) VALUES (?,10)',[(x,) for x in ('trend','rsi','breakout')]); self.conn.commit()
    def bots(self): return [dict(r) for r in self.conn.execute('SELECT * FROM bots')]
    def record_candle(self,t,p):
        if self.conn.execute('SELECT 1 FROM candles WHERE time=?',(t,)).fetchone(): return False
        self.conn.execute('INSERT INTO candles VALUES (?,?)',(t,p)); self.conn.commit(); return True
    def log(self,t,event): self.conn.execute('INSERT INTO events(time,event) VALUES (?,?)',(t,event)); self.conn.commit()
    def total_equity(self,p): return sum(b['cash']+b['sol']*p for b in self.bots())
    def execute_paper_trade(self,b,action,p,t):
        cash,sol=b['cash'],b['sol']; entry=b['entry']; pnl=None
        if action=='buy' and sol<1e-10 and cash>=1:
            spend=cash*.65; execution=p*(1+SLIP); fee=spend*FEE
            qty=(spend-fee)/execution; cash-=spend; sol=qty; entry=spend
            side='buy'; tradeprice=execution
        elif action=='sell' and sol>1e-10:
            execution=p*(1-SLIP); gross=sol*execution; fee=gross*FEE
            proceeds=gross-fee; pnl=proceeds-(entry or 0)
            cash+=proceeds; qty=sol; sol=0; entry=None
            side='sell'; tradeprice=execution
        else: return
        equity=cash+sol*p; peak=max(b['peak'],equity)
        self.conn.execute('UPDATE bots SET cash=?,sol=?,entry=?,peak=?,closed_trades=closed_trades+?,wins=wins+?,realized=realized+? WHERE id=?',(cash,sol,entry,peak,int(side=='sell'),int(pnl is not None and pnl>0),pnl or 0,b['id']))
        self.conn.execute('INSERT INTO trades(bot_id,time,side,price,quantity,fee,pnl) VALUES (?,?,?,?,?,?,?)',(b['id'],t,side,tradeprice,qty,fee,pnl))
        self.conn.commit()
