import json
import re
from pathlib import Path
from datetime import datetime, timezone
import subprocess

ROOT = Path('/home/catabolic_solutions/.openclaw/workspace')
OUT = ROOT / 'dashboard' / 'public' / 'snapshot.json'
BOARD = ROOT / 'out' / 'tradier_leaders_board.txt'
ACTIVE = ROOT / 'dashboard' / 'state' / 'active_positions.json'
QUEUE = ROOT / 'dashboard' / 'state' / 'execution_queue.json'


def read_text(path):
    return path.read_text() if path.exists() else ''


def read_json(path):
    if path.exists():
        return json.loads(path.read_text())
    return {}


def cmd(command):
    try:
        return subprocess.check_output(command, shell=True, text=True, cwd=str(ROOT)).strip()
    except Exception:
        return ''


def parse_headline(stripped):
    pattern = re.compile(
        r'^\d+\.\s+(?P<symbol>\S+)\s+(?P<option_type>CALL|PUT)\s+\|\s+Underlying\s+(?P<underlying>[\d.]+)\s+\|\s+Strike\s+(?P<strike>[\d.]+)\s+\|\s+Exp\s+(?P<exp>\S+)\s+\|\s+(?P<label>.*?)\s+\|\s+Δ\s+(?P<delta>-?[\d.]+)\s+\|\s+Bid/Ask\s+(?P<bid>[\d.]+)/(?P<ask>[\d.]+)(?P<fallback>\s+\[fallback-expiry\])?$'
    )
    m = pattern.match(stripped)
    if not m:
        return {'headline': stripped}
    data = m.groupdict()
    data['fallback'] = bool(data.get('fallback'))
    data['headline'] = stripped
    return data


def parse_board(text):
    lines = [line.rstrip() for line in text.splitlines()]
    leaders = []
    section = None
    current = None
    for line in lines:
        if line == 'Directional / Scalping Leaders':
            section = 'directional'
            continue
        if line == 'Premium / Credit Leaders':
            section = 'premium'
            continue
        if line == 'Run Notes':
            section = 'notes'
            continue
        stripped = line.strip()
        if section in ('directional', 'premium') and stripped[:2].rstrip('.').isdigit() and '. ' in stripped:
            parsed = parse_headline(stripped)
            current = {'section': section, 'details': [], **parsed}
            leaders.append(current)
            continue
        if current and line.startswith('   '):
            current['details'].append(line.strip())
            if ': ' in line:
                key, value = line.strip().split(': ', 1)
                current[key.lower()] = value
    return leaders


snapshot = {
    'updatedAt': datetime.now(timezone.utc).isoformat(),
    'systemHealth': {
        'tradierBoardPresent': BOARD.exists(),
        'tradierBoardUpdatedAt': datetime.fromtimestamp(BOARD.stat().st_mtime, tz=timezone.utc).isoformat() if BOARD.exists() else None,
        'tradierApiKeyLoaded': bool(cmd("python3 -c \"import os; print('yes' if os.environ.get('TRADIER_API_KEY') else 'no')\"") == 'yes'),
        'latestCommit': cmd('git log --oneline -n 1'),
    },
    'tradier': {
        'rawBoard': read_text(BOARD),
        'leaders': parse_board(read_text(BOARD)),
    },
    'activePositions': read_json(ACTIVE),
    'executionQueue': read_json(QUEUE),
}

OUT.write_text(json.dumps(snapshot, indent=2))
print(str(OUT))
