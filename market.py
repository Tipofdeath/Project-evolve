import requests

URL='https://api.exchange.coinbase.com/products/SOL-USD/candles'

def fetch_candles():
    r=requests.get(URL,params={'granularity':60},headers={'User-Agent':'ProjectEVOLVE-paper/1.5'},timeout=20)
    r.raise_for_status()
    rows=r.json()
    if not isinstance(rows,list): raise RuntimeError('Unexpected Coinbase response')
    candles=[]
    for row in rows:
        if not isinstance(row,list) or len(row)<6: continue
        t,low,high,open_,close,volume=row[:6]
        candles.append({'time':int(t),'low':float(low),'high':float(high),'open':float(open_),'close':float(close),'volume':float(volume)})
    return sorted(candles,key=lambda c:c['time'])
