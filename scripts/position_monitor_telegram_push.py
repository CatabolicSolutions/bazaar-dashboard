import json
import os
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / '.bazaar.env'
ALERTS_FILE = ROOT / 'out' / 'position_monitor_alerts.json'
STATE_FILE = ROOT / 'out' / 'position_monitor_push_state.json'

if ENV_FILE.exists():
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('export '):
            line = line[7:]
        if '=' in line:
            key, value = line.split('=', 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"\''))

BOT_TOKEN = os.getenv('BLOC_TELEGRAM_BOT_TOKEN') or os.getenv('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.getenv('BLOC_TELEGRAM_CHAT_ID') or os.getenv('TELEGRAM_CHAT_ID')


def load_state():
    if not STATE_FILE.exists():
        return {'sent': {}}
    return json.loads(STATE_FILE.read_text())


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding='utf-8')


def send_alert(text: str) -> bool:
    if not BOT_TOKEN or not CHAT_ID:
        return False
    r = requests.post(f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage', json={'chat_id': int(CHAT_ID), 'text': text}, timeout=15)
    return r.status_code == 200


def main():
    alerts = json.loads(ALERTS_FILE.read_text()) if ALERTS_FILE.exists() else []
    state = load_state()
    sent = state.setdefault('sent', {})
    results = []
    for alert in alerts:
        text = f"⚠️ Position Alert\n{alert['message']}\nAction: {alert['action']}"
        key = f"{alert['option_symbol']}|{alert['message']}"
        if sent.get(key):
            results.append({'skipped': True, 'key': key})
            continue
        ok = send_alert(text)
        results.append({'sent': ok, 'key': key})
        if ok:
            sent[key] = True
    save_state(state)
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
