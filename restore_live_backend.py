from pathlib import Path

src = Path('/var/www/bazaar/dashboard/scripts/serve_dashboard.py.bak.1777351989')
dst = Path('/var/www/bazaar/dashboard/scripts/serve_dashboard.py')
text = src.read_text(errors='ignore')

if 'def strategy_lab_market_data()' not in text:
    insert = """

def strategy_lab_market_data():
    path = ROOT / 'eth_scalper' / 'out_eth_market_chart_30d.json'
    data = read_json(path, {})
    prices = data.get('prices', [])
    vols = data.get('total_volumes', [])
    rows = []
    for i, pair in enumerate(prices):
        try:
            ts, price = pair
            volume = vols[i][1] if i < len(vols) else 0.0
            rows.append({'ts': ts, 'price': float(price), 'volume': float(volume or 0.0)})
        except Exception:
            continue
    return {'ok': True, 'rows': rows, 'path': str(path), 'count': len(rows)}

def strategy_lab_backtest():
    path = ROOT / 'eth_scalper' / 'backtest_results.json'
    data = read_json(path, {})
    if isinstance(data, dict):
        data.setdefault('ok', True)
        data.setdefault('path', str(path))
        return data
    return {'ok': False, 'path': str(path), 'error': 'invalid backtest payload'}

def strategy_lab_analysis():
    path = ROOT / 'eth_scalper' / 'reversal_analysis.json'
    data = read_json(path, {})
    if isinstance(data, dict):
        data.setdefault('ok', True)
        data.setdefault('path', str(path))
        return data
    return {'ok': False, 'path': str(path), 'error': 'invalid analysis payload'}
"""
    text = text.replace('def hq_history():', insert + '\n' + 'def hq_history():', 1)

old = """        if path == '/api/hq/history':
            return self._send(200, hq_history())
        if path == '/api/hq/direction':
"""
new = """        if path == '/api/hq/history':
            return self._send(200, hq_history())
        if path == '/api/strategy-lab/market-data':
            return self._send(200, strategy_lab_market_data())
        if path == '/api/strategy-lab/backtest':
            return self._send(200, strategy_lab_backtest())
        if path == '/api/strategy-lab/analysis':
            return self._send(200, strategy_lab_analysis())
        if path == '/api/hq/direction':
"""
if '/api/strategy-lab/market-data' not in text:
    text = text.replace(old, new, 1)

dst.write_text(text)
print('ok')
