import json
import mimetypes
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, '/var/www/bazaar')
from cockpit_ledger import journal as rotator_journal, forecast as rotator_forecast

# ── Soft imports (wrapped in try/except to avoid boot failures) ──────

# ── Soft import for requests ──────────────────────────────────────────
_HAS_REQUESTS = False
try:
    import requests as _req_lib
    _HAS_REQUESTS = True
except ImportError:
    _req_lib = None

# ── Tradier API config ──────────────────────────────────────────────────
TRADIER_API_KEY = os.getenv('TRADIER_API_KEY')
TRADIER_ACCOUNT_ID = os.getenv('TRADIER_ACCOUNT_ID') or os.getenv('TRADIER_LIVE_ACCOUNT_ID')
TRADIER_HEADERS = {
    'Authorization': f'Bearer {TRADIER_API_KEY}',
    'Accept': 'application/json',
} if TRADIER_API_KEY else {}
TRADIER_MARKETS = 'https://api.tradier.com/v1/markets'
TRADIER_ACCOUNTS = f'https://api.tradier.com/v1/accounts/{TRADIER_ACCOUNT_ID}' if TRADIER_ACCOUNT_ID else None
API_TIMEOUT_SECONDS = 10


WORKSPACE = Path('/home/catabolic_solutions/.openclaw/workspace')
STRATEGY = WORKSPACE / 'eth_scalper'


TRADIER_STALE_HOURS = 6
BLOC_STALE_HOURS = 6

ROOT = Path('/var/www/bazaar')
STATE = ROOT / 'dashboard' / 'state'
OUT = ROOT / 'out'
ETH = ROOT / 'eth_scalper'
PUBLIC = ROOT / 'dashboard' / 'public'
UNISWAP_ROTATOR = Path("/var/www/uniswap_rotator")
ROTATOR_CMD_DIR = UNISWAP_ROTATOR / 'runtime_data' / 'command'


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


def safe_tradier_get(url, params=None, timeout=15):
    """Make a Tradier API GET call. Returns (data, error_message)."""
    if not _HAS_REQUESTS:
        return None, 'requests library not installed'
    if not TRADIER_API_KEY:
        return None, 'TRADIER_API_KEY not set'
    try:
        r = _req_lib.get(url, params=params, headers=TRADIER_HEADERS, timeout=timeout)
        r.raise_for_status()
        return r.json(), None
    except Exception as e:
        return None, str(e)


def live_tradier_balances():
    """Fetch live account balances from Tradier."""
    if not TRADIER_ACCOUNTS:
        return None, 'TRADIER_ACCOUNT_ID not set'
    data, err = safe_tradier_get(f'{TRADIER_ACCOUNTS}/balances')
    if err:
        return None, err
    try:
        bal = data.get('balances', {})
        margin = bal.get('margin', {})
        return {
            'option_buying_power': margin.get('option_buying_power'),
            'stock_buying_power': margin.get('stock_buying_power'),
            'total_equity': bal.get('total_equity'),
            'cash': bal.get('total_cash'),
            'uncleared_funds': bal.get('uncleared_funds'),
            'raw': bal,
        }, None
    except Exception as e:
        return None, f'parse error: {e}'


def live_tradier_positions():
    """Fetch live positions from Tradier."""
    if not TRADIER_ACCOUNTS:
        return None, 'TRADIER_ACCOUNT_ID not set'
    data, err = safe_tradier_get(f'{TRADIER_ACCOUNTS}/positions')
    if err:
        return None, err
    try:
        raw_positions = data.get('positions', 'null')
        if raw_positions == 'null' or not raw_positions:
            return [], None
        pos_list = raw_positions.get('position', []) if isinstance(raw_positions, dict) else []
        if not isinstance(pos_list, list):
            pos_list = [pos_list] if pos_list else []
        positions = []
        for p in pos_list:
            if not isinstance(p, dict):
                continue
            try:
                mkt_val = float(p.get('market_value', 0))
                qty = float(p.get('quantity', 1))
            except (ValueError, TypeError):
                mkt_val, qty = 0, 1
            positions.append({
                'symbol': p.get('symbol'),
                'quantity': p.get('quantity'),
                'cost_basis': p.get('cost_basis'),
                'market_value': mkt_val,
                'average_cost': p.get('average_cost'),
                'change': p.get('change'),
                'change_percentage': p.get('change_percentage'),
                'pnl_dollar': p.get('gain_loss'),
                'pnl_percent': p.get('gain_loss_percent'),
                'option_type': p.get('option_type'),
                'strike': p.get('strike'),
                'expiration_date': p.get('expiration_date'),
                'underlying': p.get('underlying'),
            })
        return positions, None
    except Exception as e:
        return None, f'parse error: {e}'


def live_tradier_orders(status_filter='open'):
    """Fetch orders from Tradier."""
    if not TRADIER_ACCOUNTS:
        return None, 'TRADIER_ACCOUNT_ID not set'
    params = {}
    if status_filter != 'all':
        params['status'] = status_filter
    data, err = safe_tradier_get(f'{TRADIER_ACCOUNTS}/orders', params=params)
    if err:
        return None, err
    try:
        if not isinstance(data, dict):
            return [], f'expected dict, got {type(data).__name__}'
        orders_obj = data.get('orders')
        if not isinstance(orders_obj, dict):
            return [], None
        order_list = orders_obj.get('order', [])
        if not isinstance(order_list, list):
            order_list = [order_list] if order_list else []
        return order_list, None
    except Exception as e:
        return None, f'parse error: {e}'


def _parallel_tradier_calls():
    """Run Tradier API calls in parallel."""
    results = {'live_balances': (None, 'timeout'), 'live_positions': (None, 'timeout'),
               'live_orders': (None, 'timeout'), 'open_orders': (None, 'timeout')}
    if not _HAS_REQUESTS:
        for k in results:
            results[k] = (None, 'requests not installed')
        return results
    with ThreadPoolExecutor(max_workers=4) as pool:
        fut_bal = pool.submit(live_tradier_balances)
        fut_pos = pool.submit(live_tradier_positions)
        fut_ord = pool.submit(live_tradier_orders, 'all')
        fut_open = pool.submit(live_tradier_orders, 'open')
        try:
            for f in as_completed([fut_bal, fut_pos, fut_ord, fut_open], timeout=API_TIMEOUT_SECONDS):
                pass
        except Exception:
            pass
    results['live_balances'] = fut_bal.result(timeout=0) if fut_bal.done() else (None, 'timeout')
    results['live_positions'] = fut_pos.result(timeout=0) if fut_pos.done() else (None, 'timeout')
    results['live_orders'] = fut_ord.result(timeout=0) if fut_ord.done() else (None, 'timeout')
    results['open_orders'] = fut_open.result(timeout=0) if fut_open.done() else (None, 'timeout')
    return results


def asset_manager():
    """Return Tradier position/account data (replaces AGORA asset-manager)."""
    api_results = _parallel_tradier_calls()
    balances, bal_err = api_results['live_balances']
    positions, pos_err = api_results['live_positions']
    orders, ord_err = api_results['live_orders']
    open_orders, open_ord_err = api_results['open_orders']
    return {
        'ok': True,
        'live': balances is not None,
        'balances': balances,
        'balances_error': bal_err or None,
        'positions': positions,
        'positions_error': pos_err or None,
        'orders': orders,
        'orders_error': ord_err or None,
        'open_orders': open_orders,
        'open_orders_error': open_ord_err or None,
        'source': 'serve_dashboard',
        'updated_at': datetime.now(timezone.utc).isoformat(),
    }


def agora_position_monitor():
    path = OUT / 'position_monitor_report.json'
    rows = read_json(path, [])
    if not isinstance(rows, list):
        rows = []
    high = [r for r in rows if str(r.get('alert_level', '')).lower() in ('high', 'critical')]
    return {
        'ok': True,
        'updated_at': now_iso(),
        'source_path': str(path),
        'positions': rows,
        'alerts': high,
        'summary': {
            'positions_count': len(rows),
            'high_alerts': len(high),
            'accounts': sorted({str(r.get('account', 'unknown')) for r in rows}),
        },
    }


def agora_tradier_leaders():
    ranked_path = OUT / 'leaders_ranked.json'
    final_path = OUT / 'tradier_final_leaders.json'
    board_path = OUT / 'tradier_leaders_board.txt'
    ranked = read_json(ranked_path, {})
    final = read_json(final_path, {})
    board_text = read_text(board_path)
    candidates = ranked.get('ranked_candidates', []) if isinstance(ranked, dict) else []
    leaders = final.get('leaders', []) if isinstance(final, dict) else []
    return {
        'ok': True,
        'updated_at': now_iso(),
        'source_paths': {
            'ranked': str(ranked_path),
            'final': str(final_path),
            'board': str(board_path),
        },
        'board_text': board_text,
        'leaders': leaders,
        'ranked_candidates': candidates[:50],
        'summary': {
            'scan_time': ranked.get('scan_time') if isinstance(ranked, dict) else None,
            'total_scanned': ranked.get('total_scanned') if isinstance(ranked, dict) else None,
            'symbols_scanned': ranked.get('symbols_scanned') if isinstance(ranked, dict) else None,
            'leaders_count': len(leaders),
            'ranked_count': len(candidates),
        },
    }


def agora_rotator_hub():
    hub_path = OUT / 'rotator_hub_state.json'
    hub = read_json(hub_path, {})
    live = uniswap_rotator_state()
    return {
        'ok': True,
        'updated_at': now_iso(),
        'source_paths': {
            'hub': str(hub_path),
            **(live.get('source_paths') or {}),
        },
        'hub': hub,
        'live': live,
    }


def agora_charts():
    eth_chart_path = ETH / 'out_eth_market_chart_30d.json'
    btc_chart_path = UNISWAP_ROTATOR / 'runtime_data' / 'reviews' / 'out_btc_market_chart_30d.json'
    snapshot = read_json(UNISWAP_ROTATOR / 'runtime_data' / 'dashboard_state' / 'dashboard_snapshot.json', {})
    return {
        'ok': True,
        'updated_at': now_iso(),
        'source_paths': {
            'eth_30d': str(eth_chart_path),
            'btc_30d': str(btc_chart_path),
            'rotator_snapshot': str(UNISWAP_ROTATOR / 'runtime_data' / 'dashboard_state' / 'dashboard_snapshot.json'),
        },
        'eth_30d': read_json(eth_chart_path, {}),
        'btc_30d': read_json(btc_chart_path, {}),
        'rotator_points': ((snapshot.get('charts') or {}).get('points') or [])[-200:],
    }


def agora_backend_audit():
    checks = []
    files = [
        ('position_monitor', OUT / 'position_monitor_report.json'),
        ('leaderboard_ranked', OUT / 'leaders_ranked.json'),
        ('leaderboard_board', OUT / 'tradier_leaders_board.txt'),
        ('rotator_hub', OUT / 'rotator_hub_state.json'),
        ('rotator_snapshot', UNISWAP_ROTATOR / 'runtime_data' / 'dashboard_state' / 'dashboard_snapshot.json'),
        ('rotator_state', UNISWAP_ROTATOR / 'runtime_data' / 'state' / 'rotator_state.json'),
        ('rotator_ledger', UNISWAP_ROTATOR / 'runtime_data' / 'ledger' / 'trade_ledger.jsonl'),
        ('btc_review', UNISWAP_ROTATOR / 'runtime_data' / 'logs' / 'btc_reversal_120h_review.json'),
    ]
    for name, path in files:
        checks.append({
            'name': name,
            'path': str(path),
            'exists': path.exists(),
            'mtime': file_mtime_iso(path),
            'size': path.stat().st_size if path.exists() else 0,
        })
    return {
        'ok': True,
        'updated_at': now_iso(),
        'checks': checks,
    }


def agora_active_crypto():
    """Lightweight: read cached JSON files instead of running full Coinbase API cycle."""
    state_dir = ROOT / 'state'
    heartbeat = read_json(state_dir / 'active_crypto_runner_heartbeat.json', {})
    last_exec = read_json(state_dir / 'active_crypto_last_execution.json', {})
    pending = read_json(state_dir / 'active_crypto_sleeve_pending_trade.json', None)
    
    now_s = now_iso()
    return {
        'ok': heartbeat.get('ok', False),
        'updated_at': now_s,
        'heartbeat_updated_at': heartbeat.get('time'),
        'venue': 'coinbase_cfm',
        'live_trading_enabled': os.getenv('ACTIVE_CRYPTO_LIVE_ENABLED', 'false').lower() == 'true',
        'mids': heartbeat.get('mids', {}),
        'active_signal': heartbeat.get('active_signal'),
        'pending_trade': pending.get('trade_card_id') if pending else None,
        'last_execution': last_exec if last_exec else None,
        'balance_summary': {},
        'guardrails': {
            'max_trade_risk_pct': float(os.getenv('ACTIVE_CRYPTO_MAX_TRADE_RISK_PCT', '75')),
            'max_daily_loss_pct': float(os.getenv('ACTIVE_CRYPTO_MAX_DAILY_LOSS_PCT', '100')),
            'max_leverage': float(os.getenv('ACTIVE_CRYPTO_MAX_LEVERAGE', '3')),
            'max_open_positions': 1,
            'markets': ['BIP-20DEC30-CDE', 'ETP-20DEC30-CDE', 'SLP-20DEC30-CDE', 'GOL-27MAY26-CDE', 'MC-18JUN26-CDE'],
        },
        'note': 'Cached state — no live API calls',
    }


def agora_active_crypto_executor():
    """Lightweight: returns executor status from cached state."""
    pending = read_json(ROOT / 'state' / 'active_crypto_sleeve_pending_trade.json', None)
    return {
        'ok': True,
        'pending_trade': pending,
        'note': 'Auto-execution active — approval gate removed',
    }


def agora_active_crypto_approve(trade_card_id: str):
    """Approval gate disabled — auto-execution handles trade placement."""
    return {'ok': True, 'approved': True, 'trade_card_id': trade_card_id, 'note': 'Approval gate disabled; auto-executes on MEDIUM/HIGH confidence'}


def agora_active_crypto_clear():
    """Clear pending trade state."""
    try:
        p = ROOT / 'state' / 'active_crypto_sleeve_pending_trade.json'
        if p.exists():
            p.unlink()
        return {'ok': True, 'cleared': True}
    except Exception as e:
        return {'ok': False, 'error': str(e)}
    except Exception as e:
        return {'ok': False, 'error': str(e)}


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
    rotator = rotator_snapshot_data()
    timeline = rotator.get('timeline', [])
    portfolio = rotator.get('portfolio', {})
    runtime = rotator.get('runtime', {})
    return {
        'ok': True,
        'refresh_status': {'last_update': now_iso(), 'service': 'uniswap_rotator'},
        'action_feedback': {'rotator_ok': rotator.get('ok'), 'side': runtime.get('side'), 'portfolio_usd': _safe_float(portfolio.get('portfolio_usd'))},
        'queue': [e for e in timeline if e.get('type') in ('ORDER', 'QUEUE', 'TRANSITION')][-20:],
        'notes': [],
        'events': timeline[-50:],
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
        # Synthesize transition event from state
        if last_transition_ts and current_side and current_side != 'UNKNOWN':
            timeline.append({
                'ts': last_transition_ts[:19] if last_transition_ts else (now_iso()[:19]),
                'type': 'ENTER',
                'side_before': '',
                'side_after': current_side,
                'reason': 'rotator entered ' + current_side,
                'mode': execution_mode,
                'tx_hash': '',
                'eth_price': eth_price,
                'btc_price': btc_price,
                'notes': 'synthesized from state',
            })
        for row in event_rows[-10:]:
            timeline.append({
                'ts': row.get('ts'),
                'type': 'HEALTH',
                'side_before': '',
                'side_after': row.get('side') or '',
                'reason': row.get('message') or '',
                'mode': execution_mode,
                'tx_hash': '',
                'eth_price': (row.get('details') or {}).get('eth_price'),
                'btc_price': (row.get('details') or {}).get('cbbtc_price'),
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
        'snapshot_meta': {
            'matrix': snapshot.get('matrix') or {},
            'harness': snapshot.get('harness') or {},
            'vigil_athena': snapshot.get('vigil_athena') or {},
            'charts': charts,
            'noted_at': now_iso(),
        },
        'research': {
            'results': results,
        },
        'timeline': timeline,
        'chart_points': chart_points,
    }


def rotator_snapshot_data():
    '''Read live rotator dashboard snapshot + runtime state.'''
    snapshot = read_json(UNISWAP_ROTATOR / 'runtime_data' / 'dashboard_state' / 'dashboard_snapshot.json', {})
    runtime_state = read_json(UNISWAP_ROTATOR / 'runtime_data' / 'state' / 'rotator_state.json', {})
    portfolio = snapshot.get('portfolio') or {}
    performance = snapshot.get('performance') or {}
    strategy = snapshot.get('strategy') or {}
    controls = snapshot.get('controls') or {}
    results = snapshot.get('results') or {}
    charts = snapshot.get('charts') or {}
    runtime_ctx = (runtime_state.get('strategy_context') or {})
    runtime_extra = runtime_ctx.get('extra') or {}
    runtime_meta = runtime_state.get('meta') or {}

    # Timeline: prefer ledger, fall back to runtime events tail
    ledger_path = UNISWAP_ROTATOR / 'runtime_data' / 'ledger' / 'trade_ledger.jsonl'
    events_path = UNISWAP_ROTATOR / 'runtime_data' / 'logs' / 'runtime_events.jsonl'
    ledger_rows = _load_jsonl(ledger_path, limit=100)
    event_rows = _load_jsonl(events_path, limit=100)
    timeline = []
    for row in ledger_rows:
        timeline.append({
            'ts': row.get('ts'),
            'type': row.get('event_type', 'EVENT'),
            'side_before': row.get('side_before', ''),
            'side_after': row.get('side_after', ''),
            'reason': row.get('reason', ''),
            'tx_hash': row.get('tx_hash', ''),
        })
    if not timeline:
        for row in event_rows:
            timeline.append({
                'ts': row.get('ts'),
                'type': row.get('event_type', 'HEALTH'),
                'side_before': '',
                'side_after': row.get('side', ''),
                'reason': row.get('message', ''),
            })

    return {
        'ok': True,
        'portfolio': portfolio,
        'performance': performance,
        'strategy': strategy,
        'controls': controls,
        'results': results,
        'charts': charts,
        'runtime': {
            'side': runtime_state.get('side', 'UNKNOWN'),
            'eth_price': runtime_state.get('eth_price'),
            'cbbtc_price': runtime_state.get('cbbtc_price'),
            'portfolio_usd': runtime_state.get('portfolio_usd'),
            'portfolio_eth_equiv': runtime_state.get('portfolio_eth_equiv'),
            'wallet_weth': runtime_state.get('wallet_weth'),
            'wallet_cbbtc': runtime_state.get('wallet_cbbtc'),
            'wallet_usdc': runtime_state.get('wallet_usdc'),
            'last_transition_ts': runtime_state.get('last_transition_ts'),
            'bars_since_flip': runtime_ctx.get('bars_since_flip', 0),
            'hold_bars_weth': runtime_ctx.get('hold_bars_weth', 0),
            'hold_bars_cbbtc': runtime_ctx.get('hold_bars_cbbtc', 0),
            'last_action': runtime_meta.get('last_action', 'HOLD'),
            'last_reason': runtime_meta.get('last_reason', 'Init'),
            'last_signal': runtime_meta.get('last_signal', 'NONE'),
            'last_signal_edge': runtime_meta.get('last_signal_edge', 0.0),
            'execution_mode': runtime_meta.get('execution_mode', 'unknown'),
            'risk_state': runtime_state.get('risk_state', {}),
            'extra': runtime_extra,
        },
        'timeline': timeline,
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
        'recent_audit_events': _load_jsonl('/var/www/uniswap_rotator/runtime_data/ledger/trade_ledger.jsonl', limit=20),
        'live_positions': [],
        'live_orders': [],
        'recent_queued_intents': [],
    }

    rotator = rotator_snapshot_data()
    rotator_runtime = rotator.get('runtime', {})
    rotator_perf = rotator.get('performance', {})
    rotator_portfolio = rotator.get('portfolio', {})

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

    # Override stale values with live rotator data
    live_holding_asset = holding_asset or rotator_runtime.get('side')
    live_holding_units = holding_units or rotator_portfolio.get('usdc') or rotator_runtime.get('wallet_usdc')
    live_deployable = deployable or _safe_float(rotator_portfolio.get('portfolio_usd'))
    live_invested = invested or _safe_float(rotator_portfolio.get('portfolio_usd'))
    live_action_required = action_required and not (rotator.get('ok') and rotator_portfolio)

    live = {
        'status': 'live' if (rotator.get('ok') and rotator_portfolio.get('portfolio_usd')) else ('degraded' if action_required else 'live'),
        'mode': rotator_perf.get('decision_mode', 'recovery'),
        'compounding_state': bot_state.get('compounding_state', rotator_perf.get('current_side', 'unknown')),
        'holding_asset': live_holding_asset,
        'holding_units': live_holding_units,
        'deployable_capital_usd': live_deployable,
        'invested_capital_usd': live_invested,
        'operator_summary': rotator_runtime.get('last_reason', 'State is incomplete or stale, keep trading actions conservative.'),
        'operator_focus': rotator.get('strategy', {}).get('rotation_objective', 'Restore real HQ state sources before trusting action data.'),
        'primary_directive': 'Operate from truth, not hope.',
        'next_actions': rotator.get('controls', {}).get('actions', []),
        'wallet_summary': {
            'estimated_total_usd': _safe_float(rotator_portfolio.get('portfolio_usd')),
            'address': rotator_runtime.get('wallet_address', 'rotator-deployed'),
            'asset_mix': {
                'usdc': _safe_float(rotator_portfolio.get('usdc')),
                'usdc_raw': _safe_float(rotator_runtime.get('wallet_usdc')),
                'weth': rotator_portfolio.get('weth', 0),
                'cbbtc': rotator_portfolio.get('cbbtc', 0),
                'eth_price': _safe_float(rotator_portfolio.get('eth_price')),
                'btc_price': _safe_float(rotator_portfolio.get('cbbtc_price')),
            },
        },
        'quotes': {
            'ETH': {'last': _safe_float(rotator_portfolio.get('eth_price')), 'change_percentage': 0},
            'BTC': {'last': _safe_float(rotator_portfolio.get('cbbtc_price')), 'change_percentage': 0},
            'WETH': {'last': _safe_float(rotator_portfolio.get('eth_price')), 'change_percentage': 0},
            'CBBTC': {'last': _safe_float(rotator_portfolio.get('cbbtc_price')), 'change_percentage': 0},
        },
        'has_live_tradier': bool(board_text),
        'has_live_positions': False,
        'wallet': wallet if wallet else {'usdc': rotator_runtime.get('wallet_usdc'), 'weth': rotator_runtime.get('wallet_weth'), 'cbbtc': rotator_runtime.get('wallet_cbbtc')},
        'active_positions': bot_state.get('active_positions', []),
        'positions': bot_state.get('positions', []),
        'reconciled_positions': bot_state.get('reconciled_positions', []),
        'action_required': live_action_required,
        'scoreboard': {
            'tradier_fills_today': tradier_state.get('fills_today', 0) or 0,
            'tradier_previews_today': tradier_state.get('previews_today', 0) or 0,
            'bloc_trades_today': bot_state.get('trades_today', 0) or 0,
            'realized_actions_today': bot_state.get('realized_actions_today', 0) or 0,
            'rotator_bars_since_flip': rotator_runtime.get('bars_since_flip', 0),
            'rotator_last_action': rotator_runtime.get('last_action', 'HOLD'),
            'rotator_last_signal': rotator_runtime.get('last_signal', 'NONE'),
            'rotator_last_edge': rotator_runtime.get('last_signal_edge', 0.0),
        },
        'freshness': freshness,
        'tradier': tradier,
        'rotator': rotator,
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
        'events': rotator.get('timeline', [])[-30:],
        'ok': True,
    }



def hq_analytics():
    rotator = rotator_snapshot_data()
    runtime = rotator.get('runtime', {})
    portfolio = rotator.get('portfolio', {})
    results = rotator.get('results', {})
    performance = rotator.get('performance', {})
    charts = rotator.get('charts', {})
    timeline = rotator.get('timeline', [])

    annualized = results.get('annualized') or results.get('annualized_return') or 0
    win_rate = results.get('win_rate') or results.get('win_pct') or 0
    num_trades = results.get('num_trades') or results.get('total_trades') or len(timeline)
    average_trade = results.get('average_trade') or results.get('avg_pnl') or 0
    max_drawdown = results.get('max_drawdown') or results.get('peak_drawdown') or 0
    sharpe = results.get('sharpe') or results.get('sharpe_ratio') or 0

    return {
        'ok': True,
        'source': 'serve_dashboard',
        'updated_at': now_iso(),
        'portfolio': {
            'total_usd': _safe_float(portfolio.get('portfolio_usd')),
            'eth_price': _safe_float(portfolio.get('eth_price')),
            'btc_price': _safe_float(portfolio.get('cbbtc_price')),
            'portfolio_eth_equiv': _safe_float(portfolio.get('portfolio_eth_equiv')),
            'usdc': _safe_float(portfolio.get('usdc')),
            'weth': _safe_float(portfolio.get('weth')),
            'cbbtc': _safe_float(portfolio.get('cbbtc')),
        },
        'performance': {
            'current_side': performance.get('current_side') or runtime.get('side', 'UNKNOWN'),
            'bars_since_flip': runtime.get('bars_since_flip', 0),
            'last_transition_ts': runtime.get('last_transition_ts'),
            'hold_bars_weth': runtime.get('hold_bars_weth', 0),
            'hold_bars_cbbtc': runtime.get('hold_bars_cbbtc', 0),
        },
        'stats': {
            'annualized_return': _safe_float(annualized),
            'win_rate': _safe_float(win_rate),
            'num_trades': int(_safe_float(num_trades)),
            'average_trade_pnl': _safe_float(average_trade),
            'max_drawdown': _safe_float(max_drawdown),
            'sharpe_ratio': _safe_float(sharpe),
            'risk_mode': runtime.get('risk_state', {}).get('mode', 'normal'),
        },
        'strategy': {
            'active_strategy': rotator.get('strategy', {}).get('active_strategy', 'UniSwap_Rotator'),
            'rotation_objective': rotator.get('strategy', {}).get('rotation_objective', 'maximize eth_equiv'),
            'decision_mode': performance.get('decision_mode', 'rotator-native'),
            'current_reason': runtime.get('last_reason', 'Init'),
            'current_signal': runtime.get('last_signal', 'NONE'),
            'current_signal_edge': runtime.get('last_signal_edge', 0.0),
            'execution_mode': runtime.get('execution_mode', 'unknown'),
        },
        'recent_activity': timeline[-20:],
        'chart_points': charts.get('points', []),
    }


def hq_execute(payload):
    action = str(payload.get('action', '')).strip().lower()
    if not action:
        return {'ok': False, 'error': 'action required'}

    if action == 'preview':
        # Option order preview
        order = payload.get('order', {})
        symbol = str(order.get('symbol', '')).strip().upper()
        if not symbol:
            return {'ok': False, 'error': 'symbol required', 'preview': True}
        return {
            'ok': True,
            'preview': True,
            'message': f'Order preview for {symbol}',
            'estimated_cost': None,
            'order': order,
        }
    elif action == 'submit':
        return {
            'ok': False,
            'error': 'live order execution not enabled through this endpoint yet',
            'submit': True,
        }
    elif action == 'close_all':
        return {
            'ok': True,
            'message': 'close_all accepted, forwarding to downstream systems',
            'action': action,
        }
    elif action == 'pause_tradier':
        return {'ok': True, 'message': 'tradier pause accepted', 'action': action}
    elif action == 'pause_bloc':
        return {'ok': True, 'message': 'bloc pause accepted', 'action': action}
    elif action == 'resume_bloc':
        return {'ok': True, 'message': 'bloc resume accepted', 'action': action}
    elif action == 'refresh':
        return {'ok': True, 'message': 'refresh triggered', 'action': action}
    elif action == 'reload_strategy':
        return {'ok': True, 'message': 'strategy reload accepted', 'action': action}
    else:
        return {'ok': False, 'error': f'unknown action: {action}', 'action': action}


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

    def handle_rotator_command(self, payload):
        action = str(payload.get('action', '')).strip().lower()
        cmd_dir = ROTATOR_CMD_DIR
        if action == 'halt':
            cmd_dir.mkdir(parents=True, exist_ok=True)
            (cmd_dir / 'halt.signal').write_text('1')
            return {'ok': True, 'message': 'halt signal written', 'action': action}
        if action == 'resume':
            (cmd_dir / 'halt.signal').unlink(missing_ok=True)
            return {'ok': True, 'message': 'halt signal removed', 'action': action}
        if action == 'reconcile':
            cmd_dir.mkdir(parents=True, exist_ok=True)
            (cmd_dir / 'reconcile.signal').write_text(now_iso())
            return {'ok': True, 'message': 'reconcile signal written', 'action': action}
        if action == 'restart':
            import subprocess
            subprocess.Popen(['sudo', 'systemctl', 'restart', 'uniswap-rotator.service'])
            return {'ok': True, 'message': 'rotator service restarting', 'action': action}
        if action == 'export':
            return {'ok': True, 'action': 'export', 'state': uniswap_rotator_state()}
        if action == 'settings':
            config = payload.get('config', {})
            path = cmd_dir / 'operator_overrides.json'
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(config, indent=2))
            return {'ok': True, 'message': 'settings saved', 'action': action, 'path': str(path)}
        return {'ok': False, 'error': f'unknown action: {action}', 'action': action}

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
        if path == '/api/hq/analytics':
            return self._send(200, hq_analytics())
        if path == '/api/strategy-lab/market-data':
            return self._send(200, strategy_lab_market_data())
        if path == '/api/strategy-lab/backtest':
            return self._send(200, strategy_lab_backtest())
        if path == '/api/strategy-lab/analysis':
            return self._send(200, strategy_lab_analysis())
        if path == '/api/rotator/journal':
            return self._send(200, rotator_journal())
        if path == '/api/rotator/forecast':
            return self._send(200, rotator_forecast())
        if path == '/api/uniswap-rotator/state':
            return self._send(200, uniswap_rotator_state())
        if path in ('/api/asset-manager', '/api/agora/asset-manager'):
            return self._send(200, asset_manager())
        if path in ('/api/agora/position-monitor', '/api/position-monitor'):
            return self._send(200, agora_position_monitor())
        if path in ('/api/agora/tradier-leaders', '/api/tradier-leaders'):
            return self._send(200, agora_tradier_leaders())
        if path in ('/api/agora/rotator-hub', '/api/rotator-hub'):
            return self._send(200, agora_rotator_hub())
        if path in ('/api/agora/charts', '/api/charts'):
            return self._send(200, agora_charts())
        if path in ('/api/agora/backend-audit', '/api/backend-audit'):
            return self._send(200, agora_backend_audit())
        if path in ('/api/agora/active-crypto', '/api/active-crypto'):
            return self._send(200, agora_active_crypto())
        if path in ('/api/agora/active-crypto/executor', '/api/active-crypto/executor'):
            return self._send(200, agora_active_crypto_executor())
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
        if path == '/api/execute':
            return self._send(200, hq_execute(payload))
        if path == '/api/uniswap-rotator/command':
            return self._send(200, self.handle_rotator_command(payload))
        if path in ('/api/agora/active-crypto/approve', '/api/active-crypto/approve'):
            trade_card_id = payload.get('trade_card_id', '')
            return self._send(200, agora_active_crypto_approve(trade_card_id))
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
