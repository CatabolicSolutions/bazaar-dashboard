import json
import os
from datetime import datetime, time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / '.bazaar.env'
REPORT_FILE = ROOT / 'out' / 'position_monitor_report.json'
STATE_FILE = ROOT / 'out' / 'position_monitor_summary_state.json'

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
        return {'last_sent_minute_bucket': None}
    return json.loads(STATE_FILE.read_text())


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding='utf-8')


def send_text(text: str) -> bool:
    if not BOT_TOKEN or not CHAT_ID:
        return False
    r = requests.post(f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage', json={'chat_id': int(CHAT_ID), 'text': text}, timeout=15)
    return r.status_code == 200


def alert_posture(row):
    if row['state'] == 'damage_control' or row['alert_level'] == 'high':
        return 'damage-control watch'
    if row['state'] == 'strong_green':
        return 'trim watch'
    if row['state'] == 'green':
        return 'hold watch'
    return 'exit watch'


def build_summary(rows):
    lines = ['📊 Position Monitor Summary']
    for row in rows:
        lines.append(f"{row['account'].upper()} | {row['symbol']} | {row['option_symbol']}")
        lines.append(f"Posture: {row['state']} | PnL: {row['pnl_pct']:.2f}% ({row['pnl_total']:+.2f})")
        lines.append(f"Narrative: {row['narrative']}")
        lines.append(f"Alert posture: {alert_posture(row)}")
        lines.append('')
    return '\n'.join(lines).strip()


def within_market_hours(now: datetime) -> bool:
    start = time(7, 30)
    end = time(14, 5)
    return start <= now.time() <= end and now.weekday() < 5


def main():
    rows = json.loads(REPORT_FILE.read_text()) if REPORT_FILE.exists() else []
    state = load_state()
    now = datetime.now()
    if not within_market_hours(now):
        print(json.dumps({'sent': False, 'reason': 'outside_market_hours'}))
        return
    minute_bucket = f"{now:%Y-%m-%d %H}:{now.minute // 15}"
    if state.get('last_sent_minute_bucket') == minute_bucket:
        print(json.dumps({'sent': False, 'reason': 'already_sent_this_15m_bucket'}))
        return
    text = build_summary(rows)
    ok = send_text(text)
    if ok:
        state['last_sent_minute_bucket'] = minute_bucket
        save_state(state)
    print(json.dumps({'sent': ok, 'minute_bucket': minute_bucket, 'count': len(rows)}))


if __name__ == '__main__':
    main()
