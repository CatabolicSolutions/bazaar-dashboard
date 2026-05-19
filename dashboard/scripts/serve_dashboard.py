import json
import mimetypes
import os
import subprocess
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

WORKSPACE = Path('/home/catabolic_solutions/.openclaw/workspace')
STRATEGY = WORKSPACE / 'eth_scalper'


TRADIER_STALE_HOURS = 6
BLOC_STALE_HOURS = 6

ROOT = Path('/var/www/bazaar')
STATE = ROOT / 'dashboard' / 'state'
OUT = ROOT / 'out'
ETH = ROOT / 'eth_scalper'
PUBLIC = ROOT / 'dashboard' / 'public'
UNISWAP_ROTATOR = ROOT / 'UniSwap_Rotator'


def read_text(path):
    try:
        return Path(path).read_text(encoding='utf-8')
    except Exception:
        return ''


def read_lines(path):
    try:
        return Path(path).read_text(encoding='utf-8').splitlines()
    except Exception:
        return []


def read_json(path, default=None):
    default = {} if default is None else default
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except Exception:
        return default


def maybe_number(value):
    try:
        if value is None or value == '':
            return None
        return float(value)
    except Exception:
        return None


def parse_money(text):
    for token in str(text).replace(',', ' ').split():
        if token.startswith('$'):
            try:
                return float(token.replace('$', ''))
            except Exception:
                pass
    return None


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def file_mtime_iso(path):
    try:
        return datetime.fromtimestamp(Path(path).stat().st_mtime, tz=timezone.utc).isoformat()
    except Exception:
        return None


def file_mtime_dt(path):
    try:
        return datetime.fromtimestamp(Path(path).stat().st_mtime, tz=timezone.utc)
    except Exception:
        return None


def dt_to_iso(value):
    return value.isoformat() if value else None


def age_hours(value):
    if not value:
        return None
    try:
        return round((datetime.now(timezone.utc) - value).total_seconds() / 3600, 3)
    except Exception:
        return None


def load_state_file(path):
    data = read_json(path, {})
    if isinstance(data, dict):
        return data
    return {}


def tradier_sources():
    candidates = [
        STATE / 'tradier_state.json',
        STATE / 'tradier_execution_state.json',
        ROOT / 'logs' / 'tradier_audit.log',
        STATE / 'tradier_audit_log.json',
        OUT / 'tradier_leaders_board.txt',
        STATE / 'tradier_board.txt',
    ]
    state = {}
    for p in candidates:
        if p.exists():
            state[str(p)] = {
                'mtime': file_mtime_iso(p),
                'size': p.stat().st_size,
            }
    board = ''
    board_path = None
    for p in [OUT / 'tradier_leaders_board.txt', STATE / 'tradier_board.txt']:
        if p.exists():
            board = read_text(p)
            board_path = p
            break
    audit_lines = []
    audit_path = None
    for p in [ROOT / 'logs' / 'tradier_audit.log', STATE / 'tradier_audit_log.json']:
        if p.exists():
            audit_lines = read_lines(p)[-50:]
            audit_path = p
            break
    return board, audit_lines, state, board_path, audit_path


def bloc_sources():
    wallet = load_state_file(ETH / 'state' / 'wallet.json')
    bot_state = load_state_file(ETH / 'state' / 'bot_state.json')
    state_files = {}
    for p in [ETH / 'state' / 'wallet.json', ETH / 'state' / 'bot_state.json']:
        if p.exists():
            state_files[str(p)] = {
                'mtime': file_mtime_iso(p),
                'size': p.stat().st_size,
            }
    return wallet, bot_state, state_files


def compute_freshness():
    tradier_state_path = STATE / 'tradier_state.json'
    tradier_exec_path = STATE / 'tradier_execution_state.json'
    tradier_board_path = OUT / 'tradier_leaders_board.txt' if (OUT / 'tradier_leaders_board.txt').exists() else STATE / 'tradier_board.txt'
    tradier_audit_log_path = ROOT / 'logs' / 'tradier_audit.log'
    tradier_audit_json_path = STATE / 'tradier_audit_log.json'
    wallet_path = ETH / 'state' / 'wallet.json'
    bot_state_path = ETH / 'state' / 'bot_state.json'

    tradier_state = read_json(tradier_state_path, {})
    tradier_exec = read_json(tradier_exec_path, {})
    bot_state = read_json(bot_state_path, {})

    tradier_check_dt = file_mtime_dt(tradier_state_path) or file_mtime_dt(tradier_board_path)
    tradier_preview_dt = file_mtime_dt(tradier_exec_path) or file_mtime_dt(tradier_board_path)
    tradier_fill_dt = file_mtime_dt(tradier_audit_log_path) or file_mtime_dt(tradier_audit_json_path)
    bloc_wallet_dt = file_mtime_dt(wallet_path)
    bloc_state_dt = file_mtime_dt(bot_state_path)

    bloc_trade_dt = None
    updated_at = bot_state.get('updated_at')
    if updated_at:
        try:
            bloc_trade_dt = datetime.fromisoformat(str(updated_at).replace('Z', '+00:00'))
        except Exception:
            bloc_trade_dt = None
    if not bloc_trade_dt:
        bloc_trade_dt = bloc_state_dt

    tradier_age = age_hours(tradier_check_dt)
    latest_bloc_dt = max([d for d in [bloc_wallet_dt, bloc_state_dt, bloc_trade_dt] if d], default=None)
    bloc_age = age_hours(latest_bloc_dt)

    return {
        'tradier_last_checked_at': dt_to_iso(tradier_check_dt),
        'tradier_last_preview_at': dt_to_iso(tradier_preview_dt),
        'tradier_last_fill_at': dt_to_iso(tradier_fill_dt),
        'tradier_age_hours': tradier_age,
        'tradier_stale': tradier_age is None or tradier_age > TRADIER_STALE_HOURS,
        'bloc_last_trade_at': dt_to_iso(bloc_trade_dt),
        'bloc_last_state_at': dt_to_iso(bloc_state_dt),
        'bloc_last_wallet_at': dt_to_iso(bloc_wallet_dt),
        'bloc_age_hours': bloc_age,
        'bloc_stale': bloc_age is None or bloc_age > BLOC_STALE_HOURS,
        'sources': {
            'tradier_state_status': tradier_state.get('status'),
            'tradier_execution_status': tradier_exec.get('status'),
            'bloc_runtime_status': bot_state.get('status'),
        },
    }


def strategy_lab_market_data():
    path = STRATEGY / 'out_eth_market_chart_30d.json'
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
    path = STRATEGY / 'backtest_results.json'
    data = read_json(path, {})
    if isinstance(data, dict):
        data.setdefault('ok', True)
        data.setdefault('path', str(path))
        return data
    return {'ok': False, 'path': str(path), 'error': 'invalid backtest payload'}


def strategy_lab_analysis():
    path = STRATEGY / 'reversal_analysis.json'
    data = read_json(path, {})
    if isinstance(data, dict):
        data.setdefault('ok', True)
        data.setdefault('path', str(path))
        return data
    return {'ok': False, 'path': str(path), 'error': 'invalid analysis payload'}


def hq_history():
    # Recovery-safe history payload; deepen with real local event/log sources.
    return {
        'ok': True,
        'refresh_status': {},
        'action_feedback': {},
        'queue': [],
        'notes': [],
        'events': [],
    }


def _load_jsonl(path, limit=None):
    rows = []
    for line in read_lines(path):
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    if limit:
        return rows[-limit:]
    return rows


def _safe_float(value, default=0.0):
    try:
        if value in (None, ''):
            return default
        return float(value)
    except Exception:
        return default


def _age_seconds_from_iso(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return max(0, int((datetime.now(timezone.utc) - dt).total_seconds()))
    except Exception:
        return None


def uniswap_rotator_state():
    snapshot_path = UNISWAP_ROTATOR / 'runtime_data' / 'dashboard_state' / 'dashboard_snapshot.json'
    rotator_state_path = UNISWAP_ROTATOR / 'runtime_data' / 'state' / 'rotator_state.json'
    ledger_path = UNISWAP_ROTATOR / 'runtime_data' / 'ledger' / 'trade_ledger.jsonl'
    events_path = UNISWAP_ROTATOR / 'runtime_data' / 'logs' / 'runtime_events.jsonl'

    snapshot = read_json(snapshot_path, {})
    runtime_state = read_json(rotator_state_path, {})

    # If local files are empty, try fetching from the live UniSwap bot server
    if not runtime_state.get("side") and not snapshot.get("portfolio", {}).get("portfolio_usd"):
        try:
            req = Request('http://147.182.158.68:8765/api/state', headers={'Accept': 'application/json'})
            remote = json.loads(urlopen(req, timeout=5).read())
            if remote and remote.get("side"):
                runtime_state = remote
        except Exception:
            pass

    ledger_rows = _load_jsonl(ledger_path, limit=200)
    event_rows = _load_jsonl(events_path, limit=200)

    portfolio = snapshot.get('portfolio') or {}
    performance = snapshot.get('performance') or {}
    strategy = snapshot.get('strategy') or {}
    controls = snapshot.get('controls') or {}
    results = snapshot.get('results') or {}
    charts = snapshot.get('charts') or {}
    runtime_ctx = (runtime_state.get('strategy_context') or {})
    runtime_risk = (runtime_state.get('risk_state') or {})
    runtime_meta = runtime_state.get('meta') or {}
    runtime_extra = runtime_ctx.get('extra') or {}

    current_side = performance.get('current_side') or runtime_state.get('side') or 'UNKNOWN'
    action = strategy.get('current_action') or runtime_meta.get('current_action') or 'HOLD'
    reason = strategy.get('current_reason') or runtime_ctx.get('reason') or results.get('last_result') or 'No live reason available yet.'
    signal = strategy.get('current_signal') or runtime_meta.get('current_signal') or 'NONE'
    signal_edge = _safe_float(strategy.get('current_signal_edge'))
    execution_mode = controls.get('execution_mode') or runtime_meta.get('execution_mode') or 'unknown'
    service_state = controls.get('service_state') or runtime_meta.get('service_state') or 'unknown'
    last_transition_ts = performance.get('last_transition_ts') or runtime_state.get('last_transition_ts')
    last_decision_age_seconds = _age_seconds_from_iso(last_transition_ts)

    total_usd = _safe_float(portfolio.get('portfolio_usd'))
    eth_price = _safe_float(portfolio.get('eth_price') or runtime_state.get('eth_price'))
    btc_price = _safe_float(portfolio.get('cbbtc_price') or runtime_state.get('cbbtc_price'))
    portfolio_eth_equiv = _safe_float(portfolio.get('portfolio_eth_equiv') or runtime_state.get('portfolio_eth_equiv'))

    chart_points = charts.get('points') or []
    timeline = []
    for row in ledger_rows[-50:]:
        ts = row.get('ts')
        event_type = row.get('event_type') or 'EVENT'
        timeline.append({
            'ts': ts,
            'type': event_type,
            'side_before': row.get('side_before') or row.get('from_token') or '',
            'side_after': row.get('side_after') or row.get('to_token') or '',
            'reason': row.get('reason') or ((row.get('meta') or {}).get('reason')) or '',
            'mode': ((row.get('meta') or {}).get('mode')) or ('live' if str(row.get('tx_hash') or '').startswith('0x') else 'dry_run'),
            'tx_hash': row.get('tx_hash') or '',
            'eth_price': row.get('eth_price'),
            'btc_price': row.get('cbbtc_price'),
            'notes': row.get('notes') or '',
        })
    if not timeline:
        for row in event_rows[-50:]:
            timeline.append({
                'ts': row.get('ts'),
                'type': row.get('event_type') or 'HEALTH',
                'side_before': '',
                'side_after': row.get('side') or '',
                'reason': row.get('message') or '',
                'mode': execution_mode,
                'tx_hash': '',
                'eth_price': ((row.get('details') or {}).get('eth_price')),
                'btc_price': ((row.get('details') or {}).get('cbbtc_price')),
                'notes': '',
            })

    return {
        'ok': True,
        'updated_at': now_iso(),
        'source_paths': {
            'snapshot': str(snapshot_path),
            'runtime_state': str(rotator_state_path),
            'ledger': str(ledger_path),
            'events': str(events_path),
        },
        'service': {
            'status': service_state,
            'mode': execution_mode,
        },
        'summary': {
            'current_side': current_side,
            'action': action,
            'reason': reason,
            'signal': signal,
            'signal_edge': signal_edge,
            'last_decision_age_seconds': last_decision_age_seconds,
            'last_transition_ts': last_transition_ts,
            'bars_since_flip': performance.get('bars_since_flip') or runtime_ctx.get('bars_since_flip') or 0,
            'feed_confidence': 1.0 if eth_price and btc_price else 0.0,
        },
        'portfolio': {
            'weth': _safe_float(portfolio.get('weth') or runtime_state.get('wallet_weth')),
            'cbbtc': _safe_float(portfolio.get('cbbtc') or runtime_state.get('wallet_cbbtc')),
            'usdc': _safe_float(portfolio.get('usdc') or runtime_state.get('wallet_usdc')),
            'eth_price': eth_price,
            'btc_price': btc_price,
            'portfolio_usd': total_usd,
            'portfolio_eth_equiv': portfolio_eth_equiv,
        },
        'performance': {
            'current_side': current_side,
            'portfolio_usd': total_usd,
            'portfolio_eth_equiv': portfolio_eth_equiv,
            'last_transition_ts': last_transition_ts,
            'bars_since_flip': performance.get('bars_since_flip') or runtime_ctx.get('bars_since_flip') or 0,
            'risk_mode': performance.get('risk_mode') or runtime_risk.get('mode') or 'unknown',
            'eth_equiv_total': _safe_float(charts.get('eth_equiv_total')),
            'usd_total': _safe_float(charts.get('usd_total')),
        },
        'strategy': {
            'active_strategy': strategy.get('active_strategy') or 'UniSwap_Rotator canonical 3-state',
            'rotation_objective': strategy.get('rotation_objective') or 'maximize eth_equiv_delta_units',
            'decision_mode': strategy.get('decision_mode') or 'rotator-native',
            'current_reason': reason,
            'current_action': action,
            'current_signal': signal,
            'current_signal_edge': signal_edge,
            'hold_bars_weth': runtime_ctx.get('hold_bars_weth') or 0,
            'hold_bars_cbbtc': runtime_ctx.get('hold_bars_cbbtc') or 0,
            'rotate_state': runtime_extra.get('rotate_state') or {},
            'tick': runtime_extra.get('tick') or 0,
            'ema12_weth': runtime_extra.get('ema12_WETH'),
            'ema50_weth': runtime_extra.get('ema50_WETH'),
            'ema12_btc': runtime_extra.get('ema12_BTC'),
            'ema50_btc': runtime_extra.get('ema50_BTC'),
            'peak_weth': runtime_extra.get('peak_WETH'),
            'peak_btc': runtime_extra.get('peak_BTC'),
            'post_rotate_hold_until': runtime_extra.get('post_rotate_hold_until'),
            'last_flip_idx': runtime_extra.get('last_flip_idx'),
            'last_entry_idx': runtime_extra.get('last_entry_idx'),
            'q_weth': runtime_extra.get('q_weth') or [],
            'q_btc': runtime_extra.get('q_btc') or [],
            'q_history': runtime_extra.get('q_history') or [],
            'extra': runtime_extra,
        },
        'execution': {
            'mode': execution_mode,
            'transport': runtime_meta.get('transport') or 'legacy_bridge',
            'quote_status': runtime_meta.get('quote_status') or 'unknown',
            'preflight_status': runtime_meta.get('preflight_status') or 'unknown',
            'last_tx_hash': runtime_meta.get('last_tx_hash') or '',
        },
        'risk': {
            'mode': runtime_risk.get('mode') or 'unknown',
            'halted': bool(runtime_risk.get('halted')),
            'alerts': runtime_risk.get('alerts') or [],
        },
        'research': {
            'results': results,
        },
        'timeline': timeline,
        'chart_points': chart_points,
    }


def hq_status():
    board_text, audit_lines, tradier_source_state, board_path, audit_path = tradier_sources()
    wallet, bot_state, bloc_source_state = bloc_sources()
    freshness = compute_freshness()
    tradier_state = read_json(STATE / 'tradier_state.json', {})

    tradier = {
        'status': tradier_state.get('status', 'unknown'),
        'ready': bool(board_text),
        'buying_power_usd': parse_money(board_text) or tradier_state.get('buying_power_usd'),
        'positions_count': tradier_state.get('positions_count'),
        'orders_count': tradier_state.get('orders_count'),
        'top_blocker': tradier_state.get('top_blocker') or 'stale or missing live Tradier state',
        'last_check_at': freshness['tradier_last_checked_at'],
        'last_preview_at': freshness['tradier_last_preview_at'],
        'last_fill_at': freshness['tradier_last_fill_at'],
        'audit_lines': audit_lines,
    }

    tradier_board_text = board_text or read_text(STATE / 'tradier_board.txt')
    risk_config_text = read_text(ROOT / 'risk_config.json') or read_text(STATE / 'risk_config.txt')
    hq_safety_text = read_text(ROOT / 'dashboard' / 'config' / 'safety_config.json') or read_text(STATE / 'hq_safety.txt')
    bloc_wallet_text = read_text(ETH / 'state' / 'wallet.json') or read_text(STATE / 'bloc_wallet.txt')
    bloc_state_text = read_text(ETH / 'state' / 'bot_state.json') or read_text(STATE / 'bloc_state.txt')

    deployable = maybe_number(wallet.get('deployable_capital_usd')) or maybe_number(bot_state.get('deployable_capital_usd'))
    invested = maybe_number(wallet.get('invested_capital_usd')) or maybe_number(bot_state.get('invested_capital_usd'))
    holding_asset = wallet.get('holding_asset') or bot_state.get('holding_asset')
    holding_units = wallet.get('holding_units') or bot_state.get('holding_units')
    action_required = freshness['tradier_stale'] or freshness['bloc_stale'] or deployable is None or invested is None

    live = {
        'status': 'degraded' if action_required else 'live',
        'mode': 'recovery',
        'compounding_state': bot_state.get('compounding_state', 'unknown'),
        'holding_asset': holding_asset,
        'holding_units': holding_units,
        'deployable_capital_usd': deployable,
        'invested_capital_usd': invested,
        'operator_summary': 'State is incomplete or stale, keep trading actions conservative.' if action_required else 'State sources are present; verify operator actions against live integrations.',
        'operator_focus': 'Restore real HQ state sources before trusting action data.' if action_required else 'Maintain transport stability while deepening truth.',
        'primary_directive': 'Operate from truth, not hope.',
        'next_actions': ['Restore live integrations', 'Validate deploy'],
        'wallet': wallet,
        'active_positions': bot_state.get('active_positions', []),
        'positions': bot_state.get('positions', []),
        'reconciled_positions': bot_state.get('reconciled_positions', []),
        'action_required': action_required,
        'scoreboard': {
            'tradier_fills_today': tradier_state.get('fills_today', 0) or 0,
            'tradier_previews_today': tradier_state.get('previews_today', 0) or 0,
            'bloc_trades_today': bot_state.get('trades_today', 0) or 0,
            'realized_actions_today': bot_state.get('realized_actions_today', 0) or 0,
        },
        'freshness': freshness,
        'tradier': tradier,
        'artifacts': {
            'risk_config_text': risk_config_text,
            'hq_safety_text': hq_safety_text,
            'bloc_wallet_text': bloc_wallet_text,
            'bloc_state_text': bloc_state_text,
            'tradier_board_text': tradier_board_text,
            'tradier_audit_lines': audit_lines,
            'tradier_source_state': tradier_source_state,
            'bloc_source_state': bloc_source_state,
            'tradier_board_path': str(board_path) if board_path else None,
            'tradier_audit_path': str(audit_path) if audit_path else None,
        },
    }

    return {
        'source': 'serve_dashboard',
        'build': os.environ.get('BUILD', 'recovery'),
        'persistence': 'filesystem',
        'updated_at': now_iso(),
        'live': live,
        'events': [],
        'ok': True,
    }


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        data = json.dumps(obj).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def handle_command(self, payload):
        action = payload.get('action') or payload.get('command') or 'unknown'
        if action == 'refresh_truth':
            return {'ok': True, 'message': 'refresh_truth accepted', 'action': action}
        if action == 'diagnose_bloc':
            wallet, bot_state, _ = bloc_sources()
            return {'ok': True, 'message': 'bloc diagnosis complete', 'action': action, 'wallet': wallet, 'bot_state': bot_state}
        if action == 'diagnose_tradier':
            board_text, audit_lines, _ = tradier_sources()
            return {'ok': True, 'message': 'tradier diagnosis complete', 'action': action, 'board_present': bool(board_text), 'audit_lines': audit_lines[-10:]}
        if action in {'pause_tradier', 'pause_bloc', 'resume_bloc', 'close_all'}:
            return {'ok': True, 'message': f'{action} accepted', 'action': action}
        return {'ok': False, 'error': 'Unknown command', 'action': action}

    def handle_order(self, payload):
        preview = bool(payload.get('preview'))
        symbol = str(payload.get('symbol', '')).strip().upper()
        errors = []
        if not symbol:
            errors.append('symbol required')
        if preview and errors:
            return {'ok': False, 'preview': True, 'error': 'Validation failed', 'validation_errors': errors, 'order': payload}
        if preview:
            return {'ok': True, 'preview': True, 'message': 'order preview accepted', 'order': payload}
        return {'ok': False, 'preview': False, 'error': 'live order submission unavailable', 'order': payload}

    def handle_config(self, payload):
        target = str(payload.get('target', 'safety')).strip().lower()
        config = payload.get('config', {})
        if not isinstance(config, dict):
            return {'ok': False, 'error': 'config object required', 'target': target}
        if target == 'risk':
            path = ROOT / 'risk_config.json'
        else:
            path = ROOT / 'dashboard' / 'config' / 'safety_config.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(config, indent=2))
        return {'ok': True, 'message': f'config saved for {target}', 'target': target, 'path': str(path)}

    def handle_hq_action(self, payload):
        action = str(payload.get('action', '')).strip().lower()
        py = os.environ.get('PYTHON', 'python3')
        env = os.environ.copy()
        env['PYTHONPATH'] = f"{ROOT}:{env.get('PYTHONPATH','')}" if env.get('PYTHONPATH') else str(ROOT)
        if action == 'refresh_snapshot':
            cmd = [py, str(UNISWAP_ROTATOR / 'research' / 'artifacts' / 'build_inspect_page.py')]
        elif action == 'refresh_html':
            cmd = [py, str(UNISWAP_ROTATOR / 'research' / 'artifacts' / 'build_inspect_html.py')]
        elif action == 'build_hq_subpages':
            cmd = [py, str(UNISWAP_ROTATOR / 'research' / 'artifacts' / 'build_hq_subpages.py')]
        elif action == 'dry_run_runtime':
            return {'ok': False, 'error': 'dry_run_runtime not synced yet', 'action': action}
        elif action == 'transition_matrix':
            return {'ok': False, 'error': 'transition_matrix not synced yet', 'action': action}
        elif action == 'quote_bridge_check':
            return {'ok': False, 'error': 'quote_bridge_check not synced yet', 'action': action}
        else:
            return {'ok': False, 'error': 'unknown action', 'action': action}
        try:
            result = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=120, env=env)
            return {
                'ok': result.returncode == 0,
                'action': action,
                'code': result.returncode,
                'stdout': result.stdout[-4000:],
                'stderr': result.stderr[-4000:],
                'command': cmd,
            }
        except Exception as e:
            return {'ok': False, 'action': action, 'error': str(e), 'command': cmd}

    def _serve_static(self, path):
        rel = 'index.html' if path in ('', '/') else path.lstrip('/')
        file_path = (PUBLIC / rel).resolve()
        try:
            file_path.relative_to(PUBLIC.resolve())
        except Exception:
            return self._send(403, {'ok': False, 'error': 'forbidden', 'path': path})
        if file_path.is_dir():
            file_path = file_path / 'index.html'
        if not file_path.exists() or not file_path.is_file():
            return self._send(404, {'ok': False, 'error': 'not found', 'path': path})
        body = file_path.read_bytes()
        mime, _ = mimetypes.guess_type(str(file_path))
        self.send_response(200)
        self.send_header('Content-Type', mime or 'application/octet-stream')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/api/hq/status':
            return self._send(200, hq_status())
        if path == '/api/hq/history':
            return self._send(200, hq_history())
        if path == '/api/strategy-lab/market-data':
            return self._send(200, strategy_lab_market_data())
        if path == '/api/strategy-lab/backtest':
            return self._send(200, strategy_lab_backtest())
        if path == '/api/strategy-lab/analysis':
            return self._send(200, strategy_lab_analysis())
        if path == '/api/uniswap-rotator/state':
            return self._send(200, uniswap_rotator_state())
        return self._serve_static(path)

    def do_POST(self):
        path = urlparse(self.path).path
        length = int(self.headers.get('Content-Length', '0') or '0')
        try:
            payload = json.loads(self.rfile.read(length) or b'{}')
        except Exception:
            payload = {}
        if path == '/api/command':
            return self._send(200, self.handle_command(payload))
        if path == '/api/order':
            return self._send(200, self.handle_order(payload))
        if path == '/api/hq/config':
            return self._send(200, self.handle_config(payload))
        if path == '/api/hq/action':
            return self._send(200, self.handle_hq_action(payload))
        return self._send(404, {'ok': False, 'error': 'not found', 'path': path})

    def log_message(self, fmt, *args):
        return


def main():
    host = os.environ.get('HOST', '0.0.0.0')
    port = int(os.environ.get('PORT', '8765'))
    server = ThreadingHTTPServer((host, port), Handler)
    print(f'cockpit backend listening on {host}:{port}', flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
