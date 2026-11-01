"""EVOLVE daily auto dashboard: exact same strategy/positions as forward 4.6.
Never touches legacy minute-bot SQLite history. Research only.
"""
import json
from pathlib import Path
from html import escape
from evolve_shared import metadata, FORWARD_MARKETS, FORWARD_STRATEGIES

def build():
    state=json.loads(Path('paper_state_v46.json').read_text())
    report=json.loads(Path('paper_report_v46.json').read_text())
    rows=[]
    for symbol in FORWARD_MARKETS:
        for strategy in FORWARD_STRATEGIES:
            p=state['portfolios'].get(symbol+'|'+strategy)
            result=next((r for r in report.get('results',[]) if r['symbol']==symbol and r['strategy']==strategy),None)
            if p is None or result is None:
                rows.append((symbol,strategy,'Not initialized','—','—','—'))
            else:
                rows.append((symbol,strategy,p['last_day'],str(len(p['trades'])),
                             'Yes' if p['qty'] else 'No',
                             f"{result['return_pct']:+.4f}%"))
    tr=''.join('<tr>'+''.join('<td>'+escape(str(v))+'</td>' for v in row)+'</tr>' for row in rows)
    meta=metadata('daily-auto-dashboard')
    page='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>EVOLVE shared daily paper dashboard</title><style>body{font:16px system-ui;background:#0b1020;color:#f1f5ff;padding:20px}table{border-collapse:collapse;width:100%}td,th{padding:12px;border-bottom:1px solid #36445b;text-align:left}main{max-width:950px;margin:auto}small{color:#a8b7d1}</style><main><h1>EVOLVE Shared Daily Paper Bots</h1><p>Research-only. No real orders. Shared release: '''+escape(meta['shared_release'])+'''</p><p><small>Uses EVOLVE 4.6 Original and Donchian/ATR Breakout daily strategy portfolios. This is a saved snapshot, not a live dashboard. Legacy minute-trading history remains separate.</small></p><table><thead><tr><th>Market</th><th>Strategy</th><th>Last day</th><th>Closed trades</th><th>Open position</th><th>Return</th></tr></thead><tbody>'''+tr+'''</tbody></table></main></html>'''
    Path('auto_dashboard_v47.html').write_text(page,encoding='utf-8')
    Path('auto_dashboard_v47.json').write_text(json.dumps({'integration':meta,'bots':[dict(zip(('symbol','strategy','last_day','completed_trades','open_position','return_pct'),row)) for row in rows], 'errors':report.get('errors',[])},indent=2)+'\n')
if __name__=='__main__':build()
