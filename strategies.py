def rsi(prices,period=14):
    diffs=[b-a for a,b in zip(prices[:-1],prices[1:])][-period:]
    if len(diffs)<period: return 50
    gains=sum(max(d,0) for d in diffs)/period
    losses=sum(max(-d,0) for d in diffs)/period
    return 100 if losses==0 else 100-100/(1+gains/losses)

def signal(strategy,candles):
    closes=[c['close'] for c in candles]
    if len(closes)<35: return 'hold'
    if strategy=='trend':
        fast=sum(closes[-10:])/10; slow=sum(closes[-30:])/30
        return 'buy' if fast>slow*1.001 else 'sell' if fast<slow*.999 else 'hold'
    if strategy=='rsi':
        x=rsi(closes)
        return 'buy' if x<35 else 'sell' if x>65 else 'hold'
    if strategy=='breakout':
        previous=candles[-21:-1]
        return 'buy' if closes[-1]>max(c['high'] for c in previous) else 'sell' if closes[-1]<min(c['low'] for c in previous) else 'hold'
    return 'hold'
