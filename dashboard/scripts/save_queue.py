import json
import sys
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path('/home/catabolic_solutions/.openclaw/workspace')
STATE = ROOT / 'dashboard' / 'state' / 'execution_queue.json'

payload = json.load(sys.stdin)
queue = payload.get('queue', [])

cleaned = []
for q in queue:
    if not any(str(v).strip() for v in q.values() if v is not None):
        continue
    cleaned.append({
        'symbol': str(q.get('symbol', '')).strip(),
        'instrument': str(q.get('instrument', '')).strip(),
        'side': str(q.get('side', '')).strip(),
        'trigger': str(q.get('trigger', '')).strip(),
        'thesis': str(q.get('thesis', '')).strip(),
        'priority': str(q.get('priority', 'normal')).strip() or 'normal',
        'status': str(q.get('status', 'queued')).strip() or 'queued',
        'notes': str(q.get('notes', '')).strip(),
    })

out = {
    'updatedAt': datetime.now(timezone.utc).isoformat(),
    'queue': cleaned,
}
STATE.write_text(json.dumps(out, indent=2))
print(json.dumps({'ok': True, 'count': len(cleaned), 'updatedAt': out['updatedAt']}))
