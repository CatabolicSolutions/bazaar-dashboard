import json
import re
from pathlib import Path
from datetime import datetime, timezone
import subprocess
from decision_context import persist_decision_context

ROOT = Path('/home/catabolic_solutions/.openclaw/workspace')
OUT = ROOT / 'dashboard' / 'public' / 'snapshot.json'
BOARD = ROOT / 'out' / 'tradier_leaders_board.txt'
ACTIVE = ROOT / 'dashboard' / 'state' / 'active_positions.json'
QUEUE = ROOT / 'dashboard' / 'state' / 'execution_queue.json'
ACTION_FEEDBACK = ROOT / 'dashboard' / 'state' / 'action_feedback.json'
TRADIER_EXECUTION_STATE = ROOT / 'dashboard' / 'state' / 'tradier_execution_state.json'
TRADIER_AUDIT_LOG = ROOT / 'dashboard' / 'state' / 'tradier_audit_log.json'
NEAR_MISS = ROOT / 'dashboard' / 'state' / 'near_miss_candidates.json'
OUTCOME_ATTACHMENT_SUMMARY = ROOT / 'dashboard' / 'state' / 'decision_context' / 'outcome_attachment_summary.json'
CONFIDENCE_CALIBRATION_SUMMARY = ROOT / 'dashboard' / 'state' / 'decision_context' / 'confidence_calibration_summary.json'
SETUP_QUALITY_SUMMARY = ROOT / 'dashboard' / 'state' / 'decision_context' / 'setup_quality_summary.json'


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
    run_notes = []
    vix = None
    section = None
    current = None
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('VIX:'):
            vix = stripped.split(':', 1)[1].strip()
            continue
        if stripped == 'Directional / Scalping Leaders':
            section = 'directional'
            continue
        if stripped == 'Premium / Credit Leaders':
            section = 'premium'
            continue
        if stripped == 'Run Notes':
            section = 'notes'
            current = None
            continue
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
            continue
        if section == 'notes' and stripped.startswith('- '):
            run_notes.append(stripped[2:])
    return leaders, {'vix': vix, 'runNotes': run_notes}


def build_tradier_overview(leaders, board_meta):
    directional = [leader for leader in leaders if leader.get('section') == 'directional']
    premium = [leader for leader in leaders if leader.get('section') == 'premium']
    fallback = [leader for leader in leaders if leader.get('fallback')]
    return {
        'leaderCount': len(leaders),
        'directionalCount': len(directional),
        'premiumCount': len(premium),
        'fallbackCount': len(fallback),
        'vix': board_meta.get('vix'),
        'runNotes': board_meta.get('runNotes', []),
    }


raw_board = read_text(BOARD)
leaders, board_meta = parse_board(raw_board)

snapshot = {
    'updatedAt': datetime.now(timezone.utc).isoformat(),
    'systemHealth': {
        'tradierBoardPresent': BOARD.exists(),
        'tradierBoardUpdatedAt': datetime.fromtimestamp(BOARD.stat().st_mtime, tz=timezone.utc).isoformat() if BOARD.exists() else None,
        'tradierApiKeyLoaded': bool(cmd("python3 -c \"import os; print('yes' if os.environ.get('TRADIER_API_KEY') else 'no')\"") == 'yes'),
        'latestCommit': cmd('git log --oneline -n 1'),
    },
    'tradier': {
        'rawBoard': raw_board,
        'leaders': leaders,
        'overview': build_tradier_overview(leaders, board_meta),
        'runNotes': board_meta.get('runNotes', []),
        'nearMisses': read_json(NEAR_MISS),
        'actionFeedback': read_json(ACTION_FEEDBACK),
    },
    'activePositions': read_json(ACTIVE),
    'executionQueue': read_json(QUEUE),
    'tradierExecution': read_json(TRADIER_EXECUTION_STATE),
    'tradierAudit': read_json(TRADIER_AUDIT_LOG),
}

snapshot['decisionContext'] = persist_decision_context(snapshot)
snapshot['decisionOutcomeAttachments'] = read_json(OUTCOME_ATTACHMENT_SUMMARY)
snapshot['confidenceCalibration'] = read_json(CONFIDENCE_CALIBRATION_SUMMARY)
snapshot['setupQuality'] = read_json(SETUP_QUALITY_SUMMARY)

OUT.write_text(json.dumps(snapshot, indent=2))
print(str(OUT))
