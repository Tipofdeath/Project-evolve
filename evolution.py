MAX_BOTS=12

def evaluate(db,t):
    last=db.conn.execute('SELECT close FROM candles ORDER BY time DESC LIMIT 1').fetchone()
    if not last: return
    price=last[0]
    for b in db.bots():
        if not b['active']: continue
        equity=b['cash']+b['sol']*price
        peak=max(b['peak'],equity)
        db.conn.execute('UPDATE bots SET peak=? WHERE id=?',(peak,b['id']))
        if equity<=peak*.70:
            db.conn.execute('UPDATE bots SET active=0 WHERE id=?',(b['id'],))
            db.log(t,f"Bot {b['id']} deactivated at 30% drawdown")
            continue
        # Reproduction transfers existing cash, not new money; strict cap.
        count=db.conn.execute('SELECT COUNT(*) FROM bots').fetchone()[0]
        if count>=MAX_BOTS: continue
        if b['closed_trades']<20 or b['wins']/b['closed_trades']<=.5 or b['realized']<2.5 or b['cash']<17: continue
        db.conn.execute('UPDATE bots SET cash=cash-10,realized=realized-2.5,closed_trades=0,wins=0 WHERE id=?',(b['id'],))
        db.conn.execute('INSERT INTO bots(parent,generation,strategy,cash) VALUES (?,?,?,10)',(b['id'],b['generation']+1,b['strategy']))
        db.log(t,f"Bot {b['id']} reproduced")
    db.conn.commit()
