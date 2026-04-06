import json
import sys
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / 'dashboard' / 'state' / 'active_positions.json'

payload = json.load(sys.stdin)
positions = payload.get('positions', [])

cleaned = []
for p in positions:
    if not any(str(v).strip() for v in p.values() if v is not None):
        continue
    cleaned.append({
        'symbol': str(p.get('symbol', '')).strip(),
        'instrument': str(p.get('instrument', '')).strip(),
        'entry': str(p.get('entry', '')).strip(),
        'current': str(p.get('current', '')).strip(),
        'size': str(p.get('size', '')).strip(),
        'invalidation': str(p.get('invalidation', '')).strip(),
        'targets': str(p.get('targets', '')).strip(),
        'notes': str(p.get('notes', '')).strip(),
        'status': str(p.get('status', 'open')).strip() or 'open',
    })

out = {
    'updatedAt': datetime.now(timezone.utc).isoformat(),
    'positions': cleaned,
}
STATE.write_text(json.dumps(out, indent=2))
print(json.dumps({'ok': True, 'count': len(cleaned), 'updatedAt': out['updatedAt']}))
