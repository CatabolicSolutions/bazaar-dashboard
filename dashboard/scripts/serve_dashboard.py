import json
import os
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path('/var/www/bazaar')
STATE = ROOT / 'dashboard' / 'state'
OUT = ROOT / 'out'
ETH = ROOT / 'eth_scalper'


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
        OUT / 'tradier_leaders_board.txt',
        STATE / 'tradier_board.txt',
    ]
    state = {}
    for p in candidates:
        if p.exists():
            state[str(p)] = file_mtime_iso(p)
    board = ''
    for p in [OUT / 'tradier_leaders_board.txt', STATE / 'tradier_board.txt']:
        if p.exists():
            board = read_text(p)
            break
    audit_lines = []
    for p in [ROOT / 'logs' / 'tradier_audit.log', STATE / 'tradier_audit_log.json']:
        if p.exists():
            audit_lines = read_lines(p)[-50:]
            break
    return board, audit_lines, state


def bloc_sources():
    wallet = load_state_file(ETH / 'state' / 'wallet.json')
    bot_state = load_state_file(ETH / 'state' / 'bot_state.json')
    state_files = {}
    for p in [ETH / 'state' / 'wallet.json', ETH / 'state' / 'bot_state.json']:
        if p.exists():
            state_files[str(p)] = file_mtime_iso(p)
    return wallet, bot_state, state_files


def compute_freshness():
    return {
        'tradier_last_checked_at': None,
        'tradier_last_preview_at': None,
        'tradier_last_fill_at': None,
        'tradier_age_hours': None,
        'tradier_stale': True,
        'bloc_last_trade_at': None,
        'bloc_last_state_at': None,
        'bloc_last_wallet_at': None,
        'bloc_age_hours': None,
        'bloc_stale': True,
    }


def hq_history():
    return {
        'ok': True,
        'refresh_status': {},
        'action_feedback': {},
        'queue': [],
        'notes': [],
        'events': [],
    }


def hq_status():
    board_text, audit_lines, _ = tradier_sources()
    wallet, bot_state, _ = bloc_sources()
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
        'operator_summary': 'State is incomplete or stale, keep trading actions conservative.',
        'operator_focus': 'Restore real HQ state sources before trusting action data.',
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

    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/api/hq/status':
            return self._send(200, hq_status())
        if path == '/api/hq/history':
            return self._send(200, hq_history())
        return self._send(404, {'ok': False, 'error': 'not found', 'path': path})

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
        return self._send(404, {'ok': False, 'error': 'not found', 'path': path})

    def log_message(self, fmt, *args):
        return


def main():
    host = os.environ.get('HOST', '127.0.0.1')
    port = int(os.environ.get('PORT', '8765'))
    server = ThreadingHTTPServer((host, port), Handler)
    print(f'cockpit backend listening on {host}:{port}', flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
