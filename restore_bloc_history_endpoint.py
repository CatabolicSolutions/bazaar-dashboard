from pathlib import Path

p = Path('/var/www/bazaar/dashboard/scripts/serve_dashboard.py')
text = p.read_text()

if 'def bloc_history()' not in text:
    insert = '''

def bloc_history(limit: int = 720):
    path = ROOT / 'logs' / 'bloc_trace.jsonl'
    points = []
    if path.exists():
        try:
            lines = [line for line in path.read_text(errors='ignore').splitlines() if line.strip()]
            for line in lines[-limit:]:
                try:
                    points.append(json.loads(line))
                except Exception:
                    continue
        except Exception:
            pass
    return {'ok': True, 'points': points, 'count': len(points), 'path': str(path)}
'''
    text = text.replace('def strategy_lab_market_data():', insert + '\n' + 'def strategy_lab_market_data():', 1)

old = """        if path == '/api/hq/history':
            return self._send(200, hq_history())
        if path == '/api/strategy-lab/market-data':
"""
new = """        if path == '/api/hq/history':
            return self._send(200, hq_history())
        if path == '/api/bloc/history':
            return self._send(200, bloc_history())
        if path == '/api/strategy-lab/market-data':
"""
if "/api/bloc/history" not in text:
    text = text.replace(old, new, 1)

p.write_text(text)
print('ok')
