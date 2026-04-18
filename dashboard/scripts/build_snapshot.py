import json
import re
from pathlib import Path
from datetime import datetime, timezone
import subprocess
from decision_context import persist_decision_context

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'dashboard' / 'public' / 'snapshot.json'
BOARD = ROOT / 'out' / 'tradier_leaders_board.txt'
ACTIVE = ROOT / 'dashboard' / 'state' / 'active_positions.json'
QUEUE = ROOT / 'dashboard' / 'state' / 'execution_queue.json'
ACTION_FEEDBACK = ROOT / 'dashboard' / 'state' / 'action_feedback.json'
TRADIER_EXECUTION_STATE = ROOT / 'out' / 'runtime_state' / 'tradier_execution_state.json'
TRADIER_AUDIT_LOG = ROOT / 'out' / 'runtime_state' / 'tradier_audit_log.json'
LEGACY_TRADIER_EXECUTION_STATE = ROOT / 'dashboard' / 'state' / 'tradier_execution_state.json'
LEGACY_TRADIER_AUDIT_LOG = ROOT / 'dashboard' / 'state' / 'tradier_audit_log.json'
NEAR_MISS = ROOT / 'dashboard' / 'state' / 'near_miss_candidates.json'
ETH_SCALPER_BOT_STATE = ROOT / 'eth_scalper' / 'state' / 'bot_state.json'
ETH_SCALPER_POSITIONS = ROOT / 'eth_scalper' / 'state' / 'positions.json'
ETH_SCALPER_WALLET = ROOT / 'eth_scalper' / 'state' / 'wallet.json'
ETH_SCALPER_SIGNALS = ROOT / 'eth_scalper' / 'logs' / 'signals.jsonl'
ETH_SCALPER_ERRORS = ROOT / 'eth_scalper' / 'logs' / 'errors.log'
TRADIER_EXECUTION_AUDIT = ROOT / 'out' / 'tradier_execution_audit.jsonl'
BAZAAR_REFRESH_LOG = ROOT / 'out' / 'logs' / 'bazaar_refresh_cycle.log'
TRADIER_AUTO_TRADE_LOG = ROOT / 'out' / 'logs' / 'tradier_auto_trade.log'
OUTCOME_ATTACHMENT_SUMMARY = ROOT / 'dashboard' / 'state' / 'decision_context' / 'outcome_attachment_summary.json'
CONFIDENCE_CALIBRATION_SUMMARY = ROOT / 'dashboard' / 'state' / 'decision_context' / 'confidence_calibration_summary.json'
SETUP_QUALITY_SUMMARY = ROOT / 'dashboard' / 'state' / 'decision_context' / 'setup_quality_summary.json'
PREFERENCE_ACTION_BIAS_SUMMARY = ROOT / 'dashboard' / 'state' / 'decision_context' / 'preference_action_bias_summary.json'
OPERATOR_FEEDBACK_SUMMARY = ROOT / 'dashboard' / 'state' / 'operator_feedback' / 'feedback_summary.json'
FIELD_TEST_SUMMARY = ROOT / 'dashboard' / 'state' / 'field_test' / 'monday_session_summary.json'
REFRESH_STATUS_STATE = ROOT / 'dashboard' / 'state' / 'refresh_status.json'
ENV_FILE = ROOT / '.bazaar.env'


def read_text(path):
    return path.read_text() if path.exists() else ''


def read_json(path):
    if path.exists():
        return json.loads(path.read_text())
    return {}


def read_json_with_fallback(primary, fallback):
    if primary.exists():
        return json.loads(primary.read_text())
    if fallback.exists():
        return json.loads(fallback.read_text())
    return {}


def env_file_has_tradier_key():
    if not ENV_FILE.exists():
        return False
    try:
        return any(line.strip().startswith('TRADIER_API_KEY=') for line in ENV_FILE.read_text().splitlines())
    except Exception:
        return False


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


def read_jsonl_tail(path, limit=25):
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(errors='ignore').splitlines()[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            rows.append({'raw': line})
    return rows


def read_text_tail(path, limit=40):
    if not path.exists():
        return []
    return path.read_text(errors='ignore').splitlines()[-limit:]


def build_bloc_status(bot_state, wallet_state, positions_state, signal_rows, error_lines):
    last_signal = signal_rows[-1] if signal_rows else {}
    open_positions = positions_state.get('positions', []) if isinstance(positions_state, dict) else []
    last_failure = next((line for line in reversed(error_lines) if line.strip()), None)
    funded_side = 'USDC' if float(wallet_state.get('usdc', 0) or 0) > float((wallet_state.get('eth', 0) or 0)) * 1000 else 'ETH'
    return {
        'mode': bot_state.get('mode', 'unknown'),
        'status': bot_state.get('status', 'unknown'),
        'wallet': wallet_state,
        'capitalAllocation': {
            'ethUsdApprox': round(float(wallet_state.get('eth', 0) or 0) * 2200, 2),
            'usdc': round(float(wallet_state.get('usdc', 0) or 0), 2),
        },
        'fundedSide': funded_side,
        'openPositions': open_positions,
        'activePosition': open_positions[0] if open_positions else None,
        'lastAction': last_signal,
        'lastTransaction': (open_positions[0].get('tx_hash') if open_positions else None),
        'nextExpectedAction': 'monitor_open_position' if open_positions else 'await_signal_or_fallback_entry',
        'lastFailure': last_failure,
        'heartbeat': bot_state.get('status', 'unknown'),
        'automationEnabled': bot_state.get('status') == 'running',
        'haltReason': None if bot_state.get('status') == 'running' else 'bot not running',
    }


def build_trading_desk_status(execution_state, audit_state, execution_audit_rows, refresh_lines):
    intents = execution_state.get('intents', []) if isinstance(execution_state, dict) else []
    decisions = execution_state.get('riskDecisions', []) if isinstance(execution_state, dict) else []
    decision_cards = execution_state.get('decisionCards', []) if isinstance(execution_state, dict) else []
    latest_intent = intents[-1] if intents else None
    latest_decision = decisions[-1] if decisions else None
    latest_card = decision_cards[-1] if decision_cards else None
    latest_audit = execution_audit_rows[-1] if execution_audit_rows else None
    refresh_tail = [line for line in refresh_lines if line.strip()][-8:]
    return {
        'lastEvaluatedCandidate': latest_intent,
        'decisionCard': latest_card,
        'decisionResult': latest_decision.get('disposition') if latest_decision else None,
        'rejectionReason': (latest_decision.get('reasons') or [None])[0] if latest_decision else None,
        'previewState': latest_audit if latest_audit and latest_audit.get('action') == 'preview' else None,
        'liveOrderState': latest_audit if latest_audit and latest_audit.get('action') == 'place' else None,
        'fillState': latest_audit,
        'automationEnabled': True,
        'lastCycleRun': refresh_tail[-1] if refresh_tail else None,
        'refreshTail': refresh_tail,
        'auditRows': execution_audit_rows,
    }


def build_operator_journal(bloc_status, trading_desk_status, signal_rows, execution_audit_rows):
    entries = []
    for row in signal_rows[-12:]:
        entries.append({
            'ts': row.get('timestamp') or row.get('ts'),
            'system': 'bloc',
            'kind': 'signal',
            'summary': row.get('reason') or row.get('type') or row.get('direction') or 'signal',
            'payload': row,
        })
    for row in execution_audit_rows[-12:]:
        entries.append({
            'ts': row.get('ts'),
            'system': 'trading_desk',
            'kind': row.get('action', 'audit'),
            'summary': row.get('response', {}).get('order', {}).get('status') if isinstance(row.get('response'), dict) else row.get('action'),
            'payload': row,
        })
    if bloc_status.get('lastFailure'):
        entries.append({
            'ts': None,
            'system': 'bloc',
            'kind': 'failure',
            'summary': bloc_status.get('lastFailure'),
            'payload': {'raw': bloc_status.get('lastFailure')},
        })
    return sorted(entries, key=lambda x: str(x.get('ts') or ''))[-20:]


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

refresh_status = read_json(REFRESH_STATUS_STATE)
tradier_key_available = bool(cmd("python3 -c \"import os; print('yes' if os.environ.get('TRADIER_API_KEY') else 'no')\"") == 'yes') or env_file_has_tradier_key()

bloc_bot_state = read_json(ETH_SCALPER_BOT_STATE)
bloc_positions = read_json(ETH_SCALPER_POSITIONS)
bloc_wallet = read_json(ETH_SCALPER_WALLET)
bloc_signal_rows = read_jsonl_tail(ETH_SCALPER_SIGNALS)
bloc_error_lines = read_text_tail(ETH_SCALPER_ERRORS)
tradier_execution_audit_rows = read_jsonl_tail(TRADIER_EXECUTION_AUDIT)
refresh_log_tail = read_text_tail(BAZAAR_REFRESH_LOG)
tradier_auto_trade_tail = read_text_tail(TRADIER_AUTO_TRADE_LOG)
bloc_status = build_bloc_status(bloc_bot_state, bloc_wallet, bloc_positions, bloc_signal_rows, bloc_error_lines)
tradier_execution_state = read_json_with_fallback(TRADIER_EXECUTION_STATE, LEGACY_TRADIER_EXECUTION_STATE)
tradier_audit_log = read_json_with_fallback(TRADIER_AUDIT_LOG, LEGACY_TRADIER_AUDIT_LOG)
trading_desk_status = build_trading_desk_status(tradier_execution_state, tradier_audit_log, tradier_execution_audit_rows, refresh_log_tail + tradier_auto_trade_tail)
operator_journal = build_operator_journal(bloc_status, trading_desk_status, bloc_signal_rows, tradier_execution_audit_rows)

tradier_latest_intent = (tradier_execution_state.get('intents', []) or [None])[-1] if isinstance(tradier_execution_state, dict) else None
tradier_latest_audit = tradier_execution_audit_rows[-1] if tradier_execution_audit_rows else None
bloc_latest_signal = bloc_signal_rows[-1] if bloc_signal_rows else None
bloc_funded = bool((bloc_wallet or {}).get('usdc', 0) >= 25 or (bloc_wallet or {}).get('weth', 0) > 0 or (bloc_wallet or {}).get('eth', 0) > 0)
bloc_last_attempt_status = 'blocked_by_missing_edge' if bloc_latest_signal and 'edge_too_low' in str(bloc_latest_signal.get('reason')) else ('qualified' if bloc_latest_signal and bloc_latest_signal.get('executed') else 'unknown')
bloc_last_rejection_reason = bloc_latest_signal.get('reason') if bloc_latest_signal else None

snapshot = {
    'updatedAt': datetime.now(timezone.utc).isoformat(),
    'systemHealth': {
        'tradierBoardPresent': BOARD.exists(),
        'tradierBoardUpdatedAt': datetime.fromtimestamp(BOARD.stat().st_mtime, tz=timezone.utc).isoformat() if BOARD.exists() else None,
        'tradierApiKeyLoaded': tradier_key_available,
        'refreshStatus': refresh_status,
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
    'tradierExecution': tradier_execution_state,
    'tradierAudit': tradier_audit_log,
    'blocStatus': bloc_status,
    'tradingDeskStatus': trading_desk_status,
    'autonomyMonitor': {
        'lastCycleRun': trading_desk_status.get('lastCycleRun'),
        'nextCycle': 'cron / 15-minute refresh cadence',
        'heartbeat': {
            'bloc': bloc_status.get('heartbeat'),
            'tradingDesk': 'scheduled',
        },
        'lastSuccessfulAction': trading_desk_status.get('liveOrderState') or bloc_status.get('lastTransaction'),
        'lastFailure': bloc_status.get('lastFailure') or trading_desk_status.get('rejectionReason'),
        'automationEnabled': {
            'bloc': bloc_status.get('automationEnabled'),
            'tradingDesk': trading_desk_status.get('automationEnabled'),
        },
        'haltReason': {
            'bloc': bloc_status.get('haltReason'),
            'tradingDesk': None,
        },
    },
    'operatorJournal': operator_journal,
    'hq': {
        'engine_truth_board': {
            'tradier': {
                'funded': bool(tradier_key_available),
                'path_ready': True,
                'edge_proven': False,
                'status_label': 'ready_for_first_live_deployment',
                'available_capital_usd': (read_json(Path('/home/catabolic_solutions/.openclaw/workspace/out/tradier_account_state.json')) or {}).get('cash_available'),
                'last_lifecycle_stage': tradier_latest_intent.get('status') if tradier_latest_intent else None,
                'last_attempt_status': trading_desk_status.get('decisionResult'),
                'last_rejection_reason': trading_desk_status.get('rejectionReason'),
                'last_preview_ok': bool(trading_desk_status.get('previewState')),
                'last_closed_trade_net_pnl_usd': None,
                'top_blocker': trading_desk_status.get('rejectionReason'),
                'updated_at': datetime.now(timezone.utc).isoformat(),
            },
            'bloc': {
                'funded': bloc_funded,
                'path_ready': True,
                'edge_proven': False,
                'status_label': 'edge_not_proven',
                'available_capital_usd': (bloc_wallet or {}).get('usdc'),
                'last_lifecycle_stage': 'rejected' if bloc_last_rejection_reason else ('qualified' if bloc_last_attempt_status == 'qualified' else None),
                'last_attempt_status': bloc_last_attempt_status,
                'last_rejection_reason': bloc_last_rejection_reason,
                'last_meaningful_attempt_size_usd': 40.0 if bloc_last_rejection_reason else None,
                'last_gross_edge_pct': None,
                'last_estimated_friction_pct': None,
                'last_closed_trade_net_pnl_usd': None,
                'top_blocker': 'missing_edge' if bloc_last_rejection_reason else None,
                'updated_at': datetime.now(timezone.utc).isoformat(),
            }
        }
    }
}

snapshot['decisionContext'] = persist_decision_context(snapshot)
snapshot['decisionOutcomeAttachments'] = read_json(OUTCOME_ATTACHMENT_SUMMARY)
snapshot['confidenceCalibration'] = read_json(CONFIDENCE_CALIBRATION_SUMMARY)
snapshot['setupQuality'] = read_json(SETUP_QUALITY_SUMMARY)
snapshot['preferenceActionBias'] = read_json(PREFERENCE_ACTION_BIAS_SUMMARY)
snapshot['operatorFeedback'] = read_json(OPERATOR_FEEDBACK_SUMMARY)
snapshot['fieldTest'] = read_json(FIELD_TEST_SUMMARY)

OUT.write_text(json.dumps(snapshot, indent=2))
print(str(OUT))
