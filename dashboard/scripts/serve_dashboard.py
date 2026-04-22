from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
import subprocess
import os
import json
import argparse
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse
import sys

SCRIPT_DIR = Path(__file__).parent.resolve()
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import requests
from operator_feedback import append_feedback
from session_capture import append_event
from hq_repository import hq_repository
import position_manager
import trade_journal
from datetime import datetime

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

# Get the repository root based on this script's location
SCRIPT_DIR = Path(__file__).parent.resolve()
ROOT = SCRIPT_DIR.parent.parent
for candidate in (str(ROOT), str(ROOT / 'scripts'), str(ROOT / 'eth_scalper')):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

# Load environment from .bazaar.env if not already set
env_file = ROOT / '.bazaar.env'
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                # Handle both formats: export KEY=value and KEY=value
                if line.startswith('export '):
                    line = line[7:]  # Remove 'export ' prefix if present
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip().strip('"\'')
                    if key not in os.environ:
                        os.environ[key] = value
PUBLIC = ROOT / 'dashboard' / 'public'
BUILDER = ROOT / 'dashboard' / 'scripts' / 'build_snapshot.py'

from wallet_monitor import wallet_monitor
SAVE_POSITIONS = ROOT / 'dashboard' / 'scripts' / 'save_positions.py'
SAVE_QUEUE = ROOT / 'dashboard' / 'scripts' / 'save_queue.py'
EXECUTE_LEADER = ROOT / 'dashboard' / 'scripts' / 'execute_leader.py'
POSITIONS_STATE = ROOT / 'dashboard' / 'state' / 'active_positions.json'
QUEUE_STATE = ROOT / 'dashboard' / 'state' / 'execution_queue.json'
ACTION_FEEDBACK_STATE = ROOT / 'dashboard' / 'state' / 'action_feedback.json'
REFRESH_STATUS_STATE = ROOT / 'dashboard' / 'state' / 'refresh_status.json'
REFRESH_LOCK_STATE = ROOT / 'dashboard' / 'state' / 'manual_refresh.lock'
REFRESH_SCRIPT = ROOT / 'scripts' / 'bazaar_refresh_cycle.sh'


class Handler(SimpleHTTPRequestHandler):
    def refresh_snapshot(self):
        try:
            subprocess.run(['bash', '-lc', f'source ~/.profile >/dev/null 2>&1; source ~/.bashrc >/dev/null 2>&1; python3 {BUILDER}'], cwd=str(ROOT), check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

    def read_json(self, path, default):
        if path.exists():
            try:
                return json.loads(path.read_text())
            except Exception:
                return default
        return default

    def write_json(self, path, payload):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2))

    def _refresh_lock_active(self):
        if not REFRESH_LOCK_STATE.exists():
            return False
        try:
            payload = json.loads(REFRESH_LOCK_STATE.read_text())
            pid = int(payload.get('pid', 0))
            if pid > 0:
                os.kill(pid, 0)
                return True
        except Exception:
            return False
        return False

    def _write_refresh_lock(self):
        self.write_json(REFRESH_LOCK_STATE, {'pid': os.getpid(), 'updatedAt': now_iso()})

    def _clear_refresh_lock(self):
        try:
            REFRESH_LOCK_STATE.unlink(missing_ok=True)
        except Exception:
            pass

    def _canonical_refresh_payload(self, *, ok, stage, message, trigger='manual_dashboard_run', stdout_tail='', stderr_tail=''):
        snapshot = PUBLIC / 'snapshot.json'
        board = ROOT / 'out' / 'tradier_leaders_board.txt'
        payload = {
            'ok': ok,
            'stage': stage,
            'message': message,
            'updatedAt': now_iso(),
            'trigger': trigger,
            'snapshotMtime': datetime.fromtimestamp(snapshot.stat().st_mtime, tz=timezone.utc).isoformat() if snapshot.exists() else None,
            'boardMtime': datetime.fromtimestamp(board.stat().st_mtime, tz=timezone.utc).isoformat() if board.exists() else None,
        }
        if stdout_tail:
            payload['stdoutTail'] = stdout_tail[-600:]
        if stderr_tail:
            payload['stderrTail'] = stderr_tail[-600:]
        return payload

    def json_response(self, status_code, payload):
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode())

    def html_response(self, status_code, html):
        self.send_response(status_code)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))

    def _run_save(self, script_path, body):
        proc = subprocess.run(
            ['python3', str(script_path)],
            input=body,
            cwd=str(ROOT),
            capture_output=True,
            env=os.environ
        )
        if proc.returncode == 0:
            self.refresh_snapshot()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(proc.stdout)
        else:
            self.json_response(500, {'ok': False, 'error': proc.stderr.decode() or 'save failed'})

    def _record_action_feedback(self, *, leader, action, result, state_change):
        instrument = f"{leader.get('exp', '')} {leader.get('strike', '')} {leader.get('option_type', '')}".strip()
        payload = {
            'updatedAt': datetime.now(timezone.utc).isoformat(),
            'feedback': {
                'symbol': str(leader.get('symbol', '')).strip(),
                'instrument': instrument,
                'headline': str(leader.get('headline', '')).strip(),
                'action': action,
                'result': result,
                'stateChange': state_change,
            },
        }
        self.write_json(ACTION_FEEDBACK_STATE, payload)
        return payload

    def _queue_selected_leader(self, leader):
        state = self.read_json(QUEUE_STATE, {'updatedAt': None, 'queue': []})
        queue = state.get('queue', [])
        instrument = f"{leader.get('exp', '')} {leader.get('strike', '')} {leader.get('option_type', '')}".strip()
        item = {
            'symbol': str(leader.get('symbol', '')).strip(),
            'instrument': instrument,
            'side': 'buy' if leader.get('section') == 'directional' else 'sell_spread_candidate',
            'trigger': str(leader.get('entry', '')).strip(),
            'thesis': str(leader.get('thesis', '')).strip(),
            'priority': 'high' if leader.get('section') == 'directional' else 'normal',
            'status': 'queued',
            'notes': f"dashboard selected-item action | {leader.get('headline', '')}".strip(),
        }
        queue = [q for q in queue if not (q.get('symbol') == item['symbol'] and q.get('instrument') == item['instrument'] and q.get('status') == item['status'])]
        queue.insert(0, item)
        out = {
            'updatedAt': datetime.now(timezone.utc).isoformat(),
            'queue': queue,
        }
        self.write_json(QUEUE_STATE, out)
        feedback = self._record_action_feedback(
            leader=leader,
            action='queue_selected_leader',
            result='Applied local queue action',
            state_change='Selected item is now queued in local execution queue state.',
        )
        self.refresh_snapshot()
        return {
            'ok': True,
            'action': 'queue_selected_leader',
            'item': item,
            'count': len(queue),
            'updatedAt': out['updatedAt'],
            'feedback': feedback['feedback'],
        }

    def _watch_selected_leader(self, leader):
        state = self.read_json(POSITIONS_STATE, {'updatedAt': None, 'positions': []})
        positions = state.get('positions', [])
        instrument = f"{leader.get('exp', '')} {leader.get('strike', '')} {leader.get('option_type', '')}".strip()
        position = {
            'symbol': str(leader.get('symbol', '')).strip(),
            'instrument': instrument,
            'entry': str(leader.get('bid', '')).strip(),
            'current': str(leader.get('ask', '')).strip(),
            'size': '',
            'invalidation': str(leader.get('invalidation', '')).strip(),
            'targets': str(leader.get('targets', '')).strip(),
            'notes': f"dashboard watchlist action | {leader.get('headline', '')}".strip(),
            'status': 'watch',
        }
        positions = [p for p in positions if not (p.get('symbol') == position['symbol'] and p.get('instrument') == position['instrument'])]
        positions.insert(0, position)
        out = {
            'updatedAt': datetime.now(timezone.utc).isoformat(),
            'positions': positions,
        }
        self.write_json(POSITIONS_STATE, out)
        feedback = self._record_action_feedback(
            leader=leader,
            action='watch_selected_leader',
            result='Applied local watch action',
            state_change='Selected item is now tracked in local watch state.',
        )
        self.refresh_snapshot()
        return {
            'ok': True,
            'action': 'watch_selected_leader',
            'item': position,
            'count': len(positions),
            'updatedAt': out['updatedAt'],
            'feedback': feedback['feedback'],
        }

    def _handle_action(self, body):
        try:
            payload = json.loads(body.decode() or '{}')
        except Exception:
            return self.json_response(400, {'ok': False, 'error': 'invalid json'})

        action = payload.get('action')
        leader = payload.get('leader') or {}
        if not leader.get('symbol') or not leader.get('exp') or not leader.get('strike') or not leader.get('option_type'):
            return self.json_response(400, {'ok': False, 'error': 'selected leader payload missing required fields'})

        if action == 'queue_selected_leader':
            return self.json_response(200, self._queue_selected_leader(leader))
        if action == 'watch_selected_leader':
            return self.json_response(200, self._watch_selected_leader(leader))
        if action == 'execute_preview':
            return self._handle_execute_preview(leader)
        if action == 'execute_confirm':
            intent_id = payload.get('intent_id')
            if not intent_id:
                return self.json_response(400, {'ok': False, 'error': 'intent_id required for execute_confirm'})
            return self._handle_execute_confirm(intent_id)
        return self.json_response(404, {'ok': False, 'error': 'unknown action'})

    def _handle_execute_preview(self, leader):
        """Preview order execution"""
        import subprocess
        import json as json_mod
        
        proc = subprocess.run(
            ['python3', str(EXECUTE_LEADER), '--leader', json_mod.dumps(leader), '--preview'],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            env=os.environ
        )
        
        try:
            result = json_mod.loads(proc.stdout)
        except Exception:
            result = {'ok': False, 'error': proc.stderr or 'execution bridge failed', 'stdout': proc.stdout}
        
        if proc.returncode == 0 and result.get('ok'):
            # Record feedback
            feedback = self._record_action_feedback(
                leader=leader,
                action='execute_preview',
                result='Preview ready',
                state_change=f"Order preview created for {leader.get('symbol')} {leader.get('option_type')}"
            )
            result['feedback'] = feedback.get('feedback')
            return self.json_response(200, result)
        else:
            return self.json_response(500, result)
    
    def _handle_execute_confirm(self, intent_id):
        """Confirm and execute order"""
        import subprocess
        import json as json_mod
        
        proc = subprocess.run(
            ['python3', str(EXECUTE_LEADER), '--execute', intent_id],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            env=os.environ
        )
        
        try:
            result = json_mod.loads(proc.stdout)
        except Exception:
            result = {'ok': False, 'error': proc.stderr or 'execution bridge failed', 'stdout': proc.stdout}
        
        if proc.returncode == 0 and result.get('ok'):
            # Add to active positions
            position = result.get('position', {})
            if position:
                self._add_position_from_execution(position)
            return self.json_response(200, result)
        else:
            return self.json_response(500, result)
    
    def _add_position_from_execution(self, position):
        """Add executed position to active_positions.json"""
        state = self.read_json(POSITIONS_STATE, {'updatedAt': None, 'positions': []})
        positions = state.get('positions', [])
        
        # Convert execution position format to dashboard format
        position_entry = {
            'symbol': position.get('symbol', ''),
            'instrument': position.get('contract', '').split(' ', 1)[1] if ' ' in position.get('contract', '') else position.get('contract', ''),
            'entry': str(position.get('entry_price', '')),
            'current': str(position.get('entry_price', '')),
            'size': str(position.get('qty', 1)),
            'invalidation': '',
            'targets': '',
            'notes': f"Executed via dashboard | {position.get('contract', '')}",
            'status': 'open',
            'execution_time': now_iso(),
        }
        
        positions.insert(0, position_entry)
        out = {
            'updatedAt': now_iso(),
            'positions': positions,
        }
        self.write_json(POSITIONS_STATE, out)
    
    def do_GET(self):
        self.refresh_snapshot()
        parsed = urlparse(self.path)
        route_path = parsed.path or '/'
        if route_path in ('/', '/hq', '/war-room', '/war-room/', '/cc'):
            self.path = '/cc.html'
        elif route_path in ('/legacy', '/legacy/'):
            self.path = '/index.html'
        elif route_path == '/api/live-positions':
            return self._handle_live_positions()
        elif route_path == '/api/live-scanner':
            return self._handle_live_scanner()
        elif route_path == '/api/exit-predictor':
            return self._handle_exit_predictor()
        elif route_path == '/api/journal':
            return self._handle_journal()
        elif route_path == '/api/analytics':
            return self._handle_analytics()
        elif route_path == '/api/premarket':
            return self._handle_premarket()
        elif route_path == '/api/heatmap':
            return self._handle_heatmap()
        elif route_path == '/api/crypto/init':
            return self._handle_crypto_init()
        elif route_path == '/api/crypto/wallet':
            return self._handle_crypto_wallet()
        elif route_path == '/api/crypto/pairs':
            return self._handle_crypto_pairs()
        elif route_path == '/api/crypto/emergency':
            return self._handle_crypto_emergency()
        elif route_path.startswith('/api/underlying-history'):
            return self._handle_underlying_history()
        elif route_path == '/api/refresh-status':
            return self._handle_refresh_status()
        elif route_path.startswith('/api/narrative'):
            return self._handle_narrative()
        elif route_path == '/api/account':
            return self._handle_account()
        elif route_path == '/api/tradier/status':
            return self._handle_tradier_status()
        elif route_path == '/api/bloc/status':
            return self._handle_bloc_status()
        elif route_path == '/api/sie/status':
            return self._handle_sie_status()
        elif route_path == '/api/positions':
            return self._handle_positions()
        elif route_path == '/api/activity':
            return self._handle_activity()
        elif route_path == '/api/eth-scalper/status':
            return self._handle_eth_scalper_status()
        elif route_path == '/api/hq/status':
            return self._handle_hq_status()
        elif route_path == '/api/hq/overview':
            return self._handle_hq_overview()
        elif route_path == '/api/eth-scalper/trades':
            return self._handle_eth_scalper_trades()
        elif route_path == '/api/eth-scalper/positions':
            return self._handle_eth_scalper_positions()
        elif route_path == '/api/eth-scalper/signals':
            return self._handle_eth_scalper_signals()
        elif route_path == '/api/eth-scalper/wallet':
            return self._handle_eth_scalper_wallet()
        elif route_path.startswith('/eth-scalper/logs'):
            return self._serve_eth_scalper_logs()
        return super().do_GET()
    
    def _handle_underlying_history(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        symbol = (params.get('symbol', [''])[0] or '').strip().upper()
        print(f"[DIAG] underlying-history called for symbol: {symbol}")
        if not symbol:
            return self.json_response(400, {'ok': False, 'error': 'symbol required'})
        api_key = os.getenv('TRADIER_API_KEY')
        env_file = ROOT / '.bazaar.env'
        if not api_key and env_file.exists():
            for line in env_file.read_text().splitlines():
                if line.startswith('TRADIER_API_KEY='):
                    api_key = line.split('=', 1)[1].strip()
                    break
        if not api_key:
            print(f"[DIAG] No API key found")
            return self.json_response(500, {'ok': False, 'error': 'TRADIER_API_KEY not configured'})
        try:
            from datetime import timedelta
            now_utc = datetime.now(timezone.utc)
            # Use 5 minutes ago as end time to avoid "start must be before" error
            end_time = (now_utc - timedelta(minutes=5)).strftime('%Y-%m-%d %H:%M')
            start_time = (now_utc - timedelta(hours=4, minutes=5)).strftime('%Y-%m-%d %H:%M')
            print(f"[DIAG] Fetching timesales for {symbol}: {start_time} to {end_time}")
            
            res = requests.get(
                'https://api.tradier.com/v1/markets/timesales',
                params={'symbol': symbol, 'interval': '5min', 'start': start_time, 'end': end_time},
                headers={'Accept': 'application/json', 'Authorization': f'Bearer {api_key}'},
                timeout=20,
            )
            print(f"[DIAG] Tradier response status: {res.status_code}")
            
            if res.status_code != 200:
                error_text = res.text[:200] if res.text else f'HTTP {res.status_code}'
                print(f"[DIAG] Tradier error: {error_text}")
                return self.json_response(200, {'ok': True, 'symbol': symbol, 'points': [], 'error': f'Tradier API: {error_text}'})
            
            try:
                data = res.json()
            except ValueError as e:
                print(f"[DIAG] JSON parse error: {e}")
                return self.json_response(200, {'ok': True, 'symbol': symbol, 'points': [], 'error': 'Invalid JSON response from Tradier'})
            
            series_data = data.get('series', {}) if isinstance(data, dict) else {}
            if series_data is None:
                series = []
            elif isinstance(series_data, dict):
                series = series_data.get('data', []) or []
            else:
                series = series_data or []
            if isinstance(series, dict):
                series = [series]
            
            points = [{'time': p.get('time'), 'close': p.get('close')} for p in series if p and p.get('close') is not None][-40:]
            print(f"[DIAG] Returning {len(points)} points for {symbol}")
            return self.json_response(200, {'ok': True, 'symbol': symbol, 'points': points})
        except Exception as e:
            import traceback
            print(f"[DIAG] Exception in _handle_underlying_history: {e}")
            traceback.print_exc()
            return self.json_response(500, {'ok': False, 'error': str(e)})

    def _handle_refresh_status(self):
        payload = self.read_json(REFRESH_STATUS_STATE, {
            'ok': False,
            'stage': 'unknown',
            'message': 'No refresh status available',
            'updatedAt': None,
            'snapshotMtime': None,
            'boardMtime': None,
        })
        if payload.get('stage') == 'starting' and payload.get('updatedAt'):
            try:
                age = datetime.now(timezone.utc) - datetime.fromisoformat(str(payload['updatedAt']).replace('Z', '+00:00'))
                if age.total_seconds() > 300:
                    payload = self._canonical_refresh_payload(
                        ok=False,
                        stage='failed',
                        message='Refresh status was left in starting and has been marked stale by backend guardrail.',
                        trigger=payload.get('trigger', 'manual_dashboard_run'),
                    )
                    self.write_json(REFRESH_STATUS_STATE, payload)
            except Exception:
                pass
        return self.json_response(200, {'ok': True, 'data': payload})

    def _handle_live_positions(self):
        """Get live position data from Tradier"""
        import subprocess
        import json as json_mod
        
        proc = subprocess.run(
            ['python3', str(ROOT / 'dashboard' / 'scripts' / 'position_manager.py'), '--get-positions'],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            env=os.environ
        )
        
        try:
            result = json_mod.loads(proc.stdout)
        except Exception:
            result = {'ok': False, 'error': proc.stderr or 'Failed to fetch positions'}
        
        if proc.returncode == 0 and result.get('ok'):
            return self.json_response(200, result)
        else:
            return self.json_response(500, result)
    
    def _handle_live_scanner(self):
        """Get live scanner data with market data"""
        import subprocess
        import json as json_mod
        
        proc = subprocess.run(
            ['python3', str(ROOT / 'dashboard' / 'scripts' / 'market_data_feed.py'), '--scanner'],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            env=os.environ
        )
        
        try:
            result = json_mod.loads(proc.stdout)
        except Exception:
            result = {'ok': False, 'error': proc.stderr or 'Failed to fetch scanner data'}
        
        if proc.returncode == 0 and result.get('ok'):
            return self.json_response(200, result)
        else:
            return self.json_response(500, result)
    
    def _handle_exit_predictor(self):
        """Get exit predictor analysis"""
        import subprocess
        import json as json_mod
        
        proc = subprocess.run(
            ['python3', str(ROOT / 'dashboard' / 'scripts' / 'exit_predictor.py'), '--analyze'],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            env=os.environ
        )
        
        try:
            result = json_mod.loads(proc.stdout)
        except Exception:
            result = {'ok': False, 'error': proc.stderr or 'Failed to analyze positions'}
        
        if proc.returncode == 0 and result.get('ok'):
            return self.json_response(200, result)
        else:
            return self.json_response(500, result)
    
    def _handle_journal(self):
        """Get trade journal entries"""
        import subprocess
        import json as json_mod
        
        proc = subprocess.run(
            ['python3', str(ROOT / 'dashboard' / 'scripts' / 'trade_journal.py'), '--list'],
            cwd=str(ROOT),
            capture_output=True,
            text=True
        )
        
        try:
            trades = json_mod.loads(proc.stdout)
            return self.json_response(200, {'ok': True, 'trades': trades})
        except Exception:
            return self.json_response(500, {'ok': False, 'error': 'Failed to load journal'})
    
    def _handle_analytics(self):
        """Get trading analytics"""
        import subprocess
        import json as json_mod
        from urllib.parse import parse_qs, urlparse
        
        # Get period from query string
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        period = params.get('period', ['all'])[0]
        
        proc = subprocess.run(
            ['python3', str(ROOT / 'dashboard' / 'scripts' / 'trade_journal.py'), '--analytics', period],
            cwd=str(ROOT),
            capture_output=True,
            text=True
        )
        
        try:
            result = json_mod.loads(proc.stdout)
            return self.json_response(200, {'ok': True, 'analytics': result})
        except Exception:
            return self.json_response(500, {'ok': False, 'error': 'Failed to calculate analytics'})
    
    def _handle_premarket(self):
        """Get pre-market gap scan"""
        import subprocess
        import json as json_mod
        
        proc = subprocess.run(
            ['python3', str(ROOT / 'dashboard' / 'scripts' / 'premarket_scanner.py'), '--scan'],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            env=os.environ
        )
        
        try:
            result = json_mod.loads(proc.stdout)
            if result.get('ok'):
                return self.json_response(200, result)
            else:
                return self.json_response(500, result)
        except Exception as e:
            return self.json_response(500, {'ok': False, 'error': str(e)})
    
    def _handle_heatmap(self):
        """Get portfolio heatmap"""
        import subprocess
        import json as json_mod
        
        proc = subprocess.run(
            ['python3', str(ROOT / 'dashboard' / 'scripts' / 'portfolio_heatmap.py'), '--heatmap'],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            env=os.environ
        )
        
        try:
            result = json_mod.loads(proc.stdout)
            if result.get('ok'):
                return self.json_response(200, result)
            else:
                return self.json_response(500, result)
        except Exception as e:
            return self.json_response(500, {'ok': False, 'error': str(e)})
    
    def _handle_crypto_init(self):
        """Initialize crypto wallet"""
        import json as json_mod
        
        try:
            # For demo, return mock data
            # In production, this would call crypto_trader.py
            return self.json_response(200, {
                'ok': True,
                'address': '0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb',
                'eth_balance': 1.5,
                'tokens': {'USDC': 2500.0, 'DAI': 1000.0},
                'network': 'goerli',
                'emergency_stop': False
            })
        except Exception as e:
            return self.json_response(500, {'ok': False, 'error': str(e)})
    
    def _handle_crypto_wallet(self):
        """Get crypto wallet info"""
        try:
            return self.json_response(200, {
                'ok': True,
                'address': '0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb',
                'eth_balance': 1.5,
                'tokens': {'USDC': 2500.0, 'DAI': 1000.0},
                'emergency_stop': False
            })
        except Exception as e:
            return self.json_response(500, {'ok': False, 'error': str(e)})
    
    def _handle_crypto_pairs(self):
        """Get monitored crypto pairs"""
        try:
            return self.json_response(200, {
                'ok': True,
                'pairs': [
                    {'pair': 'WETH/USDC', 'quote': 1850.5},
                    {'pair': 'WETH/DAI', 'quote': 1849.8},
                    {'pair': 'WBTC/WETH', 'quote': 18.2},
                ]
            })
        except Exception as e:
            return self.json_response(500, {'ok': False, 'error': str(e)})
    
    def _handle_crypto_emergency(self):
        """Toggle emergency stop"""
        try:
            return self.json_response(200, {
                'ok': True,
                'stopped': True
            })
        except Exception as e:
            return self.json_response(500, {'ok': False, 'error': str(e)})
    
    def do_POST(self):
        length = int(self.headers.get('Content-Length', '0'))
        body = self.rfile.read(length)
        if self.path == '/api/positions':
            return self._run_save(SAVE_POSITIONS, body)
        if self.path == '/api/queue':
            return self._run_save(SAVE_QUEUE, body)
        if self.path == '/api/actions':
            return self._handle_action(body)
        if self.path == '/api/manual-refresh':
            return self._handle_manual_refresh()
        if self.path == '/api/close-position':
            return self._handle_close_position(body)
        if self.path == '/api/journal/export':
            return self._handle_journal_export()
        if self.path == '/api/crypto/wallet':
            return self._handle_crypto_wallet()
        if self.path == '/api/crypto/balance':
            return self._handle_crypto_balance()
        if self.path == '/api/crypto/quote':
            return self._handle_crypto_quote()
        if self.path == '/api/crypto/swap':
            return self._handle_crypto_swap()
        if self.path == '/api/operator-feedback':
            return self._handle_operator_feedback(body)
        if self.path == '/api/session-event':
            return self._handle_session_event(body)
        if self.path == '/api/order':
            return self._handle_order_submit(body)
        if self.path == '/api/eth-scalper/command':
            return self._handle_eth_scalper_command(body)
        if self.path == '/api/command':
            return self._handle_command(body)
        if self.path == '/api/hq/notes':
            return self._handle_hq_notes(body)
        if self.path == '/api/hq/config':
            return self._handle_hq_config(body)
        self.send_response(404)
        self.end_headers()
    
    def _handle_operator_feedback(self, body):
        try:
            payload = json.loads(body.decode() or '{}')
        except Exception:
            return self.json_response(400, {'ok': False, 'error': 'Invalid JSON'})
        try:
            result = append_feedback(payload)
            return self.json_response(200, result)
        except Exception as e:
            return self.json_response(400, {'ok': False, 'error': str(e)})

    def _handle_session_event(self, body):
        try:
            payload = json.loads(body.decode() or '{}')
        except Exception:
            return self.json_response(400, {'ok': False, 'error': 'Invalid JSON'})
        try:
            result = append_event(payload)
            return self.json_response(200, result)
        except Exception as e:
            return self.json_response(400, {'ok': False, 'error': str(e)})

    def _handle_manual_refresh(self):
        if self._refresh_lock_active():
            status = self._canonical_refresh_payload(
                ok=False,
                stage='running',
                message='Manual refresh already in progress',
            )
            self.write_json(REFRESH_STATUS_STATE, status)
            return self.json_response(409, {'ok': False, 'error': status['message'], 'data': status})

        payload = self._canonical_refresh_payload(
            ok=False,
            stage='starting',
            message='Manual refresh queued',
        )
        self.write_json(REFRESH_STATUS_STATE, payload)
        self._write_refresh_lock()

        try:
            try:
                proc = subprocess.run(
                    ['bash', str(REFRESH_SCRIPT)],
                    cwd=str(ROOT),
                    capture_output=True,
                    text=True,
                    timeout=180,
                    env=os.environ
                )
            except subprocess.TimeoutExpired as err:
                status = self._canonical_refresh_payload(
                    ok=False,
                    stage='timeout',
                    message='Manual refresh timed out after 180s',
                    stdout_tail=(err.stdout or '') if isinstance(err.stdout, str) else '',
                    stderr_tail=(err.stderr or '') if isinstance(err.stderr, str) else '',
                )
                self.write_json(REFRESH_STATUS_STATE, status)
                return self.json_response(504, {'ok': False, 'error': status['message'], 'data': status})

            tradier_refresh = None
            tradier_refresh_error = None
            bloc_state = ROOT / 'eth_scalper' / 'state' / 'bot_state.json'
            wallet_state = ROOT / 'eth_scalper' / 'state' / 'wallet.json'
            trades_log = ROOT / 'eth_scalper' / 'logs' / 'trades.jsonl'
            bloc_state_data = self.read_json(bloc_state, {}) if bloc_state.exists() else {}
            wallet_state_data = self.read_json(wallet_state, {}) if wallet_state.exists() else {}
            last_trade_timestamp = None
            if trades_log.exists():
                try:
                    last_line = trades_log.read_text(errors='ignore').splitlines()[-1]
                    last_trade_timestamp = json.loads(last_line).get('timestamp') if last_line else None
                except Exception:
                    last_trade_timestamp = None
            bloc_snapshot = {
                'bot_state_exists': bloc_state.exists(),
                'wallet_exists': wallet_state.exists(),
                'bot_state_updated_at': bloc_state_data.get('updated_at'),
                'wallet_updated_at': wallet_state_data.get('updated_at'),
                'wallet_address': wallet_state_data.get('address'),
                'last_trade_timestamp': last_trade_timestamp,
                'status': bloc_state_data.get('status'),
                'mode': bloc_state_data.get('mode'),
            }

            try:
                tradier_proc = subprocess.run(
                    ['python3', str(ROOT / 'scripts' / 'tradier_account.py'), 'ready'],
                    cwd=str(ROOT),
                    capture_output=True,
                    text=True,
                    timeout=45,
                    env=os.environ,
                )
                if tradier_proc.returncode == 0:
                    tradier_refresh = json.loads(tradier_proc.stdout or '{}')
                else:
                    tradier_refresh_error = (tradier_proc.stderr or tradier_proc.stdout or 'tradier account refresh failed').strip()[-400:]
            except Exception as exc:
                tradier_refresh_error = str(exc)

            if proc.returncode == 0:
                self.refresh_snapshot()
                status = self._canonical_refresh_payload(
                    ok=True,
                    stage='complete',
                    message='Manual refresh completed',
                    stdout_tail=proc.stdout or '',
                    stderr_tail=((proc.stderr or '') + ('\n' + tradier_refresh_error if tradier_refresh_error else '')),
                )
                if tradier_refresh is not None:
                    status['tradierAccount'] = tradier_refresh
                if tradier_refresh_error:
                    status['tradierRefreshError'] = tradier_refresh_error
                status['blocSnapshot'] = bloc_snapshot
                self.write_json(REFRESH_STATUS_STATE, status)
                return self.json_response(200, {'ok': True, 'data': status, 'message': status['message']})

            status = self._canonical_refresh_payload(
                ok=False,
                stage='failed',
                message=((proc.stderr or proc.stdout or 'Manual refresh failed').strip()[-400:]) or 'Manual refresh failed',
                stdout_tail=proc.stdout or '',
                stderr_tail=((proc.stderr or '') + ('\n' + tradier_refresh_error if tradier_refresh_error else '')),
            )
            if tradier_refresh is not None:
                status['tradierAccount'] = tradier_refresh
            if tradier_refresh_error:
                status['tradierRefreshError'] = tradier_refresh_error
            status['blocSnapshot'] = bloc_snapshot
            self.write_json(REFRESH_STATUS_STATE, status)
            return self.json_response(500, {'ok': False, 'error': status['message'], 'data': status})
        finally:
            self._clear_refresh_lock()

    def _handle_close_position(self, body):
        """Close a position"""
        import subprocess
        import json as json_mod
        
        try:
            payload = json_mod.loads(body.decode() or '{}')
        except Exception:
            return self.json_response(400, {'ok': False, 'error': 'Invalid JSON'})
        
        required = ['symbol', 'quantity', 'option_type', 'strike', 'expiration']
        for field in required:
            if field not in payload:
                return self.json_response(400, {'ok': False, 'error': f'Missing field: {field}'})
        
        proc = subprocess.run(
            [
                'python3', str(ROOT / 'dashboard' / 'scripts' / 'position_manager.py'),
                '--close',
                '--symbol', str(payload['symbol']),
                '--quantity', str(payload['quantity']),
                '--option-type', str(payload['option_type']),
                '--strike', str(payload['strike']),
                '--expiration', str(payload['expiration'])
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            env=os.environ
        )
        
        try:
            result = json_mod.loads(proc.stdout)
        except Exception:
            result = {'ok': False, 'error': proc.stderr or 'Failed to close position'}
        
        if proc.returncode == 0 and result.get('ok'):
            return self.json_response(200, result)
        else:
            return self.json_response(500, result)
    
    def _handle_journal_export(self):
        """Export journal to CSV"""
        import subprocess
        import json as json_mod
        
        proc = subprocess.run(
            ['python3', str(ROOT / 'dashboard' / 'scripts' / 'trade_journal.py'), '--export-csv'],
            cwd=str(ROOT),
            capture_output=True,
            text=True
        )
        
        try:
            # Parse the output to get the file path
            output = proc.stdout.strip()
            if 'Exported to:' in output:
                path = output.split('Exported to:')[1].strip()
                return self.json_response(200, {'ok': True, 'path': path})
            else:
                return self.json_response(500, {'ok': False, 'error': 'Export failed'})
        except Exception as e:
            return self.json_response(500, {'ok': False, 'error': str(e)})

    def _handle_narrative(self):
        """Generate trade narrative for selected symbol"""
        from urllib.parse import parse_qs, urlparse
        import json as json_mod
        
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        symbol = (params.get('symbol', [''])[0] or '').strip().upper()
        
        if not symbol:
            return self.json_response(400, {'ok': False, 'error': 'symbol required'})
        
        # Get leader data from current snapshot
        leader = None
        if currentSnapshot and currentSnapshot.get('tradier', {}).get('leaders'):
            for l in currentSnapshot['tradier']['leaders']:
                if l.get('symbol') == symbol:
                    leader = l
                    break
        
        if not leader:
            # Return default narrative structure
            return self.json_response(200, {
                'ok': True,
                'symbol': symbol,
                'narrative': None,
                'error': 'Leader not found in current snapshot'
            })
        
        # Import and call narrative engine
        try:
            from narrative_engine import generate_narrative
            narrative = generate_narrative(symbol, leader)
            return self.json_response(200, {
                'ok': True,
                'symbol': symbol,
                'narrative': narrative
            })
        except Exception as e:
            return self.json_response(500, {'ok': False, 'error': str(e)})

    def _handle_account(self):
        """Get account info (buying power)"""
        import requests
        
        api_key = os.getenv('TRADIER_API_KEY')
        account_id = os.getenv('TRADIER_ACCOUNT_ID')
        
        if not api_key or not account_id:
            return self.json_response(500, {'ok': False, 'error': 'API credentials not configured'})
        
        try:
            response = requests.get(
                f'https://api.tradier.com/v1/accounts/{account_id}/balances',
                headers={'Authorization': f'Bearer {api_key}', 'Accept': 'application/json'}
            )
            
            if response.status_code == 200:
                data = response.json()
                balances = data.get('balances', {})
                return self.json_response(200, {
                    'ok': True,
                    'buying_power': balances.get('option_buying_power', 0),
                    'account_value': balances.get('total_equity', 0),
                    'cash': balances.get('cash_available', 0)
                })
            else:
                return self.json_response(500, {'ok': False, 'error': f'API error: {response.status_code}'})
        except Exception as e:
            return self.json_response(500, {'ok': False, 'error': str(e)})

    def _handle_order_submit(self, body):
        """Submit order to Tradier"""
        import json as json_mod
        from order_entry import OrderRequest, OrderValidator, OrderManager
        
        try:
            payload = json_mod.loads(body.decode() or '{}')
        except Exception:
            return self.json_response(400, {'ok': False, 'error': 'Invalid JSON'})
        
        # Build order request
        try:
            order = OrderRequest(
                symbol=payload.get('symbol', ''),
                option_type=payload.get('option_type', 'call'),
                strike=float(payload.get('strike', 0)),
                expiration=payload.get('expiration', ''),
                side=payload.get('side', 'buy_to_open'),
                quantity=int(payload.get('quantity', 0)),
                order_type=payload.get('order_type', 'market'),
                limit_price=float(payload.get('limit_price')) if payload.get('limit_price') else None,
                stop_price=float(payload.get('stop_price')) if payload.get('stop_price') else None,
                time_in_force=payload.get('time_in_force', 'day')
            )
        except Exception as e:
            return self.json_response(400, {'ok': False, 'error': f'Invalid order data: {str(e)}'})
        
        # Get current price for validation
        current_price = float(payload.get('current_price', 0))
        
        # Validate
        validator = OrderValidator()
        validation = validator.validate(order, current_price)
        
        if not validation['valid']:
            return self.json_response(400, {
                'ok': False,
                'error': 'Validation failed',
                'validation_errors': validation['errors']
            })
        
        # Submit order
        manager = OrderManager()
        result = manager.submit_order(order)
        
        if result['ok']:
            return self.json_response(200, {
                'ok': True,
                'order_id': result.get('order_id'),
                'status': result.get('status'),
                'position_value': validation['position_value']
            })
        else:
            return self.json_response(500, result)

    # ETH Scalper API Endpoints
    def _handle_eth_scalper_status(self):
        """Get ETH scalper bot status"""
        try:
            state_file = ROOT / 'eth_scalper' / 'state' / 'bot_state.json'
            if state_file.exists():
                state = json.loads(state_file.read_text())
            else:
                state = {
                    'status': 'unknown',
                    'pnl': {'today': 0, 'total': 0},
                    'requests': {'used': 0, 'limit': 900}
                }
            current_wallet_data = wallet_monitor.get_all_balances()
            wallet = current_wallet_data
            live_inventory = state.get('live_inventory') or {}
            reconciled_positions = state.get('reconciled_positions') or []
            invested_capital = float(live_inventory.get('invested_capital_usd') or 0.0)
            if invested_capital <= 0:
                cbbtc_units = float(wallet.get('cbbtc') or 0.0)
                weth_units = float(wallet.get('weth') or 0.0)
                invested_capital = (cbbtc_units * float(wallet.get('cbbtc_price_usd', wallet.get('btc_price_usd', 0.0)) or 0.0)) + (weth_units * float(wallet.get('eth_price_usd') or 0.0))
            has_inventory_hold = bool(reconciled_positions) or bool(live_inventory.get('has_active_inventory_position')) or invested_capital > 0
            if has_inventory_hold and not state.get('open_positions'):
                state['open_positions'] = 1
            state['invested_capital_usd'] = round(invested_capital, 2)
            state['compounding_state'] = 'holding_active_inventory' if has_inventory_hold else ('flat_deployable' if float(state.get('available_capital') or 0.0) > 0 else 'idle_unfunded')
            return self.json_response(200, state)
        except Exception as e:
            return self.json_response(500, {'ok': False, 'error': str(e)})

    def _build_hq_live_payload(self):
        state_file = ROOT / 'eth_scalper' / 'state' / 'bot_state.json'
        positions_file = ROOT / 'eth_scalper' / 'state' / 'positions.json'
        state = json.loads(state_file.read_text()) if state_file.exists() else {}
        current_wallet_data = wallet_monitor.get_all_balances()
        wallet = current_wallet_data
        positions = json.loads(positions_file.read_text()) if positions_file.exists() else {'positions': []}
        live_inventory = state.get('live_inventory') or {}
        reconciled_positions = state.get('reconciled_positions') or []
        holding_asset = 'CBBTC' if float(wallet.get('cbbtc') or 0.0) > 1e-8 else ('WETH' if float(wallet.get('weth') or 0.0) > 1e-12 else None)
        holding_units = wallet.get('cbbtc') if holding_asset == 'CBBTC' else (wallet.get('weth') if holding_asset == 'WETH' else None)
        invested_capital = float(live_inventory.get('invested_capital_usd') or 0.0)
        if invested_capital <= 0:
            invested_capital = (
                float(wallet.get('cbbtc') or 0.0) * float(wallet.get('cbbtc_price_usd', wallet.get('btc_price_usd', 0.0)) or 0.0)
            ) + (
                float(wallet.get('weth') or 0.0) * float(wallet.get('eth_price_usd') or 0.0)
            )
        if invested_capital <= 0:
            invested_capital = float(wallet.get('estimated_total_usd') or 0.0)

        tradier_state_path = ROOT / 'out' / 'tradier_account_state.json'
        tradier_state = json.loads(tradier_state_path.read_text()) if tradier_state_path.exists() else {}
        tradier_buying_power = (
            tradier_state.get('option_buying_power')
            or tradier_state.get('cash_available')
            or tradier_state.get('total_cash')
            or (tradier_state.get('balances', {}) if isinstance(tradier_state.get('balances', {}), dict) else {}).get('total_cash')
            or (tradier_state.get('balances', {}) if isinstance(tradier_state.get('balances', {}), dict) else {}).get('cash_available')
            or tradier_state.get('buying_power')
            or 0.0
        )
        tradier_positions = tradier_state.get('positions') or []
        tradier_orders = tradier_state.get('orders') or []
        tradier_ready = bool(tradier_state.get('ready_for_options_execution')) or float(tradier_buying_power or 0.0) > 0
        tradier_blockers = tradier_state.get('blockers') or []
        tradier_blocker = None if tradier_ready else (tradier_blockers[0] if tradier_blockers else 'No Tradier buying power detected.')

        def parse_iso(value):
            if not value:
                return None
            try:
                return datetime.fromisoformat(str(value).replace('Z', '+00:00'))
            except Exception:
                return None

        now_dt = datetime.now(timezone.utc)
        tradier_last_checked_at = parse_iso(tradier_state.get('checked_at'))
        tradier_last_audit_ts = None
        tradier_last_fill_ts = None
        tradier_last_preview_ts = None
        tradier_audit_path = ROOT / 'out' / 'tradier_execution_audit.jsonl'
        if tradier_audit_path.exists():
            for line in tradier_audit_path.read_text(errors='ignore').splitlines()[-300:]:
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                ts = parse_iso(row.get('ts'))
                action = str(row.get('action') or '').lower()
                if ts and (tradier_last_audit_ts is None or ts > tradier_last_audit_ts):
                    tradier_last_audit_ts = ts
                if action == 'preview' and ts and (tradier_last_preview_ts is None or ts > tradier_last_preview_ts):
                    tradier_last_preview_ts = ts
                response = row.get('response') or {}
                order = (response.get('orders') or {}).get('order') if isinstance(response.get('orders'), dict) else response.get('order')
                if isinstance(order, dict):
                    status_text = str(order.get('status') or '').lower()
                    tx_ts = parse_iso(order.get('transaction_date') or order.get('create_date')) or ts
                    if status_text == 'filled' and tx_ts and (tradier_last_fill_ts is None or tx_ts > tradier_last_fill_ts):
                        tradier_last_fill_ts = tx_ts

        bloc_state_updated_at = parse_iso(state.get('updated_at'))
        wallet_state_path = ROOT / 'eth_scalper' / 'state' / 'wallet.json'
        wallet_state = json.loads(wallet_state_path.read_text()) if wallet_state_path.exists() else {}
        bloc_wallet_updated_at = parse_iso(wallet_state.get('updated_at'))
        bloc_last_trade_ts = None
        bloc_trades_path = ROOT / 'eth_scalper' / 'logs' / 'trades.jsonl'
        if bloc_trades_path.exists():
            for line in bloc_trades_path.read_text(errors='ignore').splitlines()[-300:]:
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                message = str(row.get('message') or '').lower()
                ts = parse_iso(row.get('timestamp'))
                if not ts:
                    continue
                if any(term in message for term in ['buy', 'sell', 'swap', 'filled', 'executed', 'submitted trade']):
                    if bloc_last_trade_ts is None or ts > bloc_last_trade_ts:
                        bloc_last_trade_ts = ts

        def age_hours(dt):
            if not dt:
                return None
            return round((now_dt - dt.astimezone(timezone.utc)).total_seconds() / 3600.0, 2)

        bloc_runtime_ts = max([dt for dt in [bloc_state_updated_at, bloc_wallet_updated_at] if dt is not None], default=None)
        tradier_stale = (age_hours(tradier_last_fill_ts or tradier_last_preview_ts or tradier_last_audit_ts or tradier_last_checked_at) or 999) >= 24
        bloc_stale = (age_hours(bloc_runtime_ts) or 999) >= 24
        zero_action_today = (state.get('daily_trades') or 0) == 0 and tradier_last_fill_ts is None
        action_required = tradier_stale and bloc_stale and zero_action_today

        cleaned_positions = []
        for pos in reconciled_positions:
            status = str(pos.get('status') or '').lower()
            allocation_state = str(pos.get('allocation_state') or '').lower()
            if status == 'closed' or allocation_state == 'closed':
                continue
            asset = str(pos.get('binding_asset') or pos.get('asset') or '').upper()
            allocated_units = float(pos.get('allocated_units') or pos.get('binding_units') or pos.get('lot_units') or 0.0)
            if asset == 'CBBTC' and allocated_units > 0:
                cleaned_positions.append({
                    'asset': 'CBBTC',
                    'units': allocated_units,
                    'entry_price': pos.get('entry_price'),
                    'target_price': pos.get('target_price'),
                    'stop_price': pos.get('stop_price'),
                    'status': pos.get('status') or 'holding_active_inventory',
                    'source': pos.get('source'),
                })
        if not cleaned_positions and holding_asset and holding_units:
            cleaned_positions.append({
                'asset': holding_asset,
                'units': holding_units,
                'entry_price': None,
                'target_price': None,
                'stop_price': None,
                'status': 'holding_active_inventory',
                'source': 'wallet_truth',
            })

        wallet_usdc = float(wallet.get('usdc', 0.0) or 0.0)
        deployable_capital = wallet_usdc
        if not cleaned_positions:
            deployable_capital = float(state.get('available_capital') or wallet_usdc or 0.0)
        compounding_state = 'holding_active_inventory' if (holding_asset or cleaned_positions) else ('flat_deployable' if deployable_capital > 0 else 'idle_unfunded')
        realized_actions_today = (0 if tradier_last_fill_ts is None or tradier_last_fill_ts.date() != now_dt.date() else 1) + int(state.get('daily_trades') or 0)
        trade_dead = tradier_stale and bloc_stale and realized_actions_today == 0
        primary_directive = (
            'Action required: both engines are economically stale. Restore real trading behavior, not just process uptime.'
            if trade_dead
            else (
                'Bloc inventory is live. Manage recycle path and stop treating this as a dead engine.'
                if compounding_state == 'holding_active_inventory'
                else ('Tradier is funded. Hunt only clean, high-clarity setups.' if tradier_ready else 'Stay flat. Restore readiness and wait for valid edge.')
            )
        )
        next_actions = []
        if trade_dead:
            next_actions = [
                {'title': 'Acknowledge economic staleness', 'detail': 'No real fills are happening. Treat dead execution as the failure state, not silent uptime.'},
                {'title': 'Force Tradier diagnosis', 'detail': f'Last Tradier fill/attempt is stale. Buying power currently shows ${float(tradier_buying_power or 0.0):.2f}.'},
                {'title': 'Force Bloc diagnosis', 'detail': 'Bloc is alive but not cycling capital. Verify wallet truth, execution path, and stale inventory logic.'},
            ]
        elif compounding_state == 'holding_active_inventory':
            next_actions = [
                {'title': 'Supervise active inventory', 'detail': f'{holding_asset or "Inventory"} is deployed. Focus on recycle path, not fresh entry.'},
                {'title': 'Verify live mark and invalidation', 'detail': 'Confirm current mark, target, and stop before adding any new risk.'},
                {'title': 'Keep Tradier separate', 'detail': 'Do not treat Bloc inventory as permission to force an options trade.'},
            ]
        elif tradier_ready:
            next_actions = [
                {'title': 'Scan for Tradier edge', 'detail': f'Buying power available: ${float(tradier_buying_power or 0.0):.2f}.'},
                {'title': 'Demand setup clarity', 'detail': 'Only act on contracts with clean structure, liquidity, and explicit invalidation.'},
                {'title': 'Log the decision', 'detail': 'If no trade, record the blocker instead of filling the screen with noise.'},
            ]
        else:
            next_actions = [
                {'title': 'Restore funded readiness', 'detail': 'No deployable Tradier capital or valid funded state is visible.'},
                {'title': 'Check runtime truth', 'detail': 'Confirm account state, balances, and position sync before trading.'},
                {'title': 'Do not improvise', 'detail': 'A quiet dashboard is better than a lying dashboard.'},
            ]
        return {
            'source': 'serve_dashboard',
            'build': 'HQv11-executive-command-center-2026-04-22',
            'persistence': 'postgresql' if hq_repository.enabled else 'memory-only',
            'updated_at': now_iso(),
            'live': {
                'status': state.get('status', 'unknown'),
                'mode': state.get('mode', 'unknown'),
                'compounding_state': compounding_state,
                'holding_asset': holding_asset,
                'holding_units': holding_units,
                'deployable_capital_usd': round(deployable_capital, 2),
                'invested_capital_usd': round(invested_capital, 2),
                'operator_summary': (
                    'Both engines are stale and no realized action is visible.'
                    if action_required
                    else (
                        f'Holding {holding_asset} inventory, service live, manage recycle and exit quality.'
                        if compounding_state == 'holding_active_inventory' and holding_asset
                        else ('Deployable cash available for next entry.' if deployable_capital > 0 else 'No funded deployable state detected.')
                    )
                ),
                'operator_focus': (
                    'Intervene directly, stale systems should not be allowed to masquerade as healthy.'
                    if action_required
                    else (
                        'Supervise live inventory, protect gains, and recycle only on valid edge.'
                        if compounding_state == 'holding_active_inventory'
                        else ('Wait for valid edge and funded conditions.' if deployable_capital > 0 else 'Restore funding or runtime prerequisites.')
                    )
                ),
                'primary_directive': primary_directive,
                'next_actions': next_actions,
                'wallet': wallet,
                'active_positions': len(cleaned_positions) or (1 if compounding_state == 'holding_active_inventory' else 0),
                'positions': cleaned_positions,
                'reconciled_positions': cleaned_positions,
                'action_required': action_required,
                'scoreboard': {
                    'tradier_fills_today': 0 if tradier_last_fill_ts is None or tradier_last_fill_ts.date() != now_dt.date() else 1,
                    'tradier_previews_today': 0 if tradier_last_preview_ts is None or tradier_last_preview_ts.date() != now_dt.date() else 1,
                    'bloc_trades_today': int(state.get('daily_trades') or 0),
                    'realized_actions_today': (0 if tradier_last_fill_ts is None or tradier_last_fill_ts.date() != now_dt.date() else 1) + int(state.get('daily_trades') or 0),
                },
                'freshness': {
                    'tradier_last_checked_at': tradier_last_checked_at.isoformat() if tradier_last_checked_at else None,
                    'tradier_last_preview_at': tradier_last_preview_ts.isoformat() if tradier_last_preview_ts else None,
                    'tradier_last_fill_at': tradier_last_fill_ts.isoformat() if tradier_last_fill_ts else None,
                    'tradier_age_hours': age_hours(tradier_last_fill_ts or tradier_last_preview_ts or tradier_last_audit_ts or tradier_last_checked_at),
                    'tradier_stale': tradier_stale,
                    'bloc_last_trade_at': bloc_last_trade_ts.isoformat() if bloc_last_trade_ts else None,
                    'bloc_last_state_at': bloc_state_updated_at.isoformat() if bloc_state_updated_at else None,
                    'bloc_last_wallet_at': bloc_wallet_updated_at.isoformat() if bloc_wallet_updated_at else None,
                    'bloc_age_hours': age_hours(bloc_runtime_ts),
                    'bloc_stale': bloc_stale,
                },
                'tradier': {
                    'ready': tradier_ready,
                    'status': 'ready' if tradier_ready else 'idle',
                    'buying_power_usd': round(float(tradier_buying_power or 0.0), 2),
                    'positions_count': len(tradier_positions) if isinstance(tradier_positions, list) else 0,
                    'orders_count': len(tradier_orders) if isinstance(tradier_orders, list) else 0,
                    'top_blocker': tradier_blocker,
                },
                'artifacts': {
                    'tradier_board_text': (ROOT / 'out' / 'tradier_leaders_board.txt').read_text(errors='ignore')[:4000] if (ROOT / 'out' / 'tradier_leaders_board.txt').exists() else 'No Tradier leaders board yet.',
                    'tradier_audit_lines': (ROOT / 'out' / 'tradier_execution_audit.jsonl').read_text(errors='ignore').splitlines()[-20:] if (ROOT / 'out' / 'tradier_execution_audit.jsonl').exists() else [],
                    'bloc_state_text': (ROOT / 'eth_scalper' / 'state' / 'bot_state.json').read_text(errors='ignore')[:4000] if (ROOT / 'eth_scalper' / 'state' / 'bot_state.json').exists() else '{}',
                    'bloc_wallet_text': (ROOT / 'eth_scalper' / 'state' / 'wallet.json').read_text(errors='ignore')[:4000] if (ROOT / 'eth_scalper' / 'state' / 'wallet.json').exists() else '{}',
                    'risk_config_text': (ROOT / 'risk_config.json').read_text(errors='ignore')[:4000] if (ROOT / 'risk_config.json').exists() else '{}',
                    'hq_safety_text': (ROOT / 'dashboard' / 'config' / 'safety_config.json').read_text(errors='ignore')[:4000] if (ROOT / 'dashboard' / 'config' / 'safety_config.json').exists() else '{}',
                },
                'controls': {
                    'deploy': [
                        {'action': 'refresh_truth', 'label': 'Refresh Truth', 'kind': 'primary', 'note': 'Rebuild live HQ state from runtime files and APIs.'},
                        {'action': 'diagnose_tradier', 'label': 'Diagnose Tradier', 'kind': 'secondary', 'note': 'Inspect options readiness, board, and execution path.'},
                        {'action': 'diagnose_bloc', 'label': 'Diagnose Bloc', 'kind': 'secondary', 'note': 'Inspect wallet truth and onchain runtime state.'},
                    ],
                    'execution': [
                        {'action': 'pause_tradier', 'label': 'Pause Tradier', 'kind': 'danger', 'note': 'Stop automated Tradier activity.'},
                        {'action': 'pause_bloc', 'label': 'Pause Bloc', 'kind': 'danger', 'note': 'Stop automated Bloc activity.'},
                        {'action': 'resume_bloc', 'label': 'Resume Bloc', 'kind': 'primary', 'note': 'Resume Bloc compounding cycle.'},
                        {'action': 'close_all', 'label': 'Emergency Close', 'kind': 'danger', 'note': 'Flatten risk immediately if supported.'},
                    ],
                },
                'system': {
                    'build_label': 'HQv11-executive-command-center-2026-04-22',
                    'presentation_mode': 'executive-operator',
                    'truth_status': 'stale' if action_required else 'live',
                },
            }
        }

    def _handle_hq_status(self):
        try:
            payload = self._build_hq_live_payload()
            hq_repository.create_tables()
            hq_repository.append_snapshot(payload)
            latest = hq_repository.get_latest_snapshot() or payload
            latest['build'] = payload.get('build')
            latest['persistence'] = payload.get('persistence')
            latest['source'] = payload.get('source')
            latest['updated_at'] = payload.get('updated_at')
            latest['live'] = payload.get('live', latest.get('live', {}))
            latest['events'] = hq_repository.get_recent_events(limit=12)
            return self.json_response(200, latest)
        except Exception as e:
            return self.json_response(200, self._build_hq_live_payload())

    def _handle_war_room_page(self):
        payload = self._build_hq_live_payload()
        try:
            hq_repository.create_tables()
            hq_repository.append_snapshot(payload)
            latest = hq_repository.get_latest_snapshot() or payload
            latest['build'] = payload.get('build')
            latest['persistence'] = payload.get('persistence')
            latest['source'] = payload.get('source')
            latest['updated_at'] = payload.get('updated_at')
            latest['live'] = payload.get('live', latest.get('live', {}))
            latest['events'] = hq_repository.get_recent_events(limit=12)
            payload = latest
        except Exception:
            pass

        live = payload.get('live') or {}
        wallet = live.get('wallet') or {}
        positions = live.get('positions') or []
        events = payload.get('events') or []
        tradier = live.get('tradier') or {}
        freshness = live.get('freshness') or {}
        scoreboard = live.get('scoreboard') or {}
        action_required = bool(live.get('action_required'))
        next_actions_data = live.get('next_actions') or []
        holding_asset = live.get('holding_asset') or 'Inventory'
        risk_config_path = ROOT / 'risk_config.json'
        hq_safety_path = ROOT / 'dashboard' / 'config' / 'safety_config.json'
        tradier_board_path = ROOT / 'out' / 'tradier_leaders_board.txt'
        bloc_state_path = ROOT / 'eth_scalper' / 'state' / 'bot_state.json'
        bloc_wallet_path = ROOT / 'eth_scalper' / 'state' / 'wallet.json'
        tradier_audit_path = ROOT / 'out' / 'tradier_execution_audit.jsonl'
        tradier_board_text = tradier_board_path.read_text(errors='ignore')[:4000] if tradier_board_path.exists() else 'No Tradier leaders board yet.'
        risk_config_text = risk_config_path.read_text(errors='ignore') if risk_config_path.exists() else '{}'
        hq_safety_text = hq_safety_path.read_text(errors='ignore') if hq_safety_path.exists() else '{}'
        bloc_state_text = bloc_state_path.read_text(errors='ignore')[:4000] if bloc_state_path.exists() else '{}'
        bloc_wallet_text = bloc_wallet_path.read_text(errors='ignore')[:4000] if bloc_wallet_path.exists() else '{}'
        tradier_audit_lines = tradier_audit_path.read_text(errors='ignore').splitlines()[-20:] if tradier_audit_path.exists() else []
        holding_units = live.get('holding_units')
        invested = float(live.get('invested_capital_usd') or 0.0)
        deployable = float(live.get('deployable_capital_usd') or 0.0)
        active_positions = int(live.get('active_positions') or len(positions) or 0)
        status = str(live.get('compounding_state') or 'unknown')
        persistence = payload.get('persistence') or 'memory-only'
        updated_at = payload.get('updated_at') or now_iso()
        operator_summary = live.get('operator_summary') or 'Waiting for live system truth.'
        operator_focus = live.get('operator_focus') or 'Pulling live system truth.'
        primary_directive = live.get('primary_directive') or operator_focus
        wallet_eth_price = wallet.get('eth_price_usd') or wallet.get('eth_price')
        reality_feed = ('ETH ' + (f"${float(wallet_eth_price):.2f}" if wallet_eth_price not in (None, '', 'nan') else '--') + ' | Wallet ' + str(wallet.get('address') or '--'))
        tradier_buying_power = tradier.get('buying_power_usd') or 0.0
        tradier_status = 'Ready' if tradier.get('ready') else 'Idle'
        sql_status = 'PostgreSQL live' if persistence == 'postgresql' else 'Memory only'
        sql_detail = 'HQ snapshots and events are being persisted.' if persistence == 'postgresql' else 'DATABASE_URL/SQLAlchemy path not live, so HQ history is transient.'
        tradier_age = freshness.get('tradier_age_hours')
        bloc_age = freshness.get('bloc_age_hours')

        def age_label(hours):
            if hours is None:
                return 'unknown'
            try:
                return f'{float(hours):.1f}h ago'
            except Exception:
                return 'unknown'

        def esc(value):
            text = '' if value is None else str(value)
            return (text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;'))

        def money(value):
            try:
                return f"${float(value):.2f}"
            except Exception:
                return '--'

        positions_html = ''.join([
            f'''<div class="position-row"><div class="position-top"><div>{esc((pos.get('asset') or holding_asset))} HOLD</div><div>{money(invested)}</div></div><div class="meta-row"><span>Units: {esc(pos.get('units') if pos.get('units') is not None else holding_units if holding_units is not None else '--')}</span><span>Status: {esc('active compounding inventory' if (pos.get('status') or status) == 'holding_active_inventory' else (pos.get('status') or status).replace('_',' '))}</span><span>Source: {esc('inventory reconciliation' if (pos.get('source') or 'wallet_truth') in {'inventory_reconciliation','wallet_truth'} else (pos.get('source') or 'wallet truth').replace('_',' '))}</span></div></div>'''
            for pos in positions
        ]) or f'''<div class="position-row"><div class="position-top"><div>{esc(holding_asset)} HOLD</div><div>{money(invested)}</div></div><div class="meta-row"><span>Units: {esc(holding_units if holding_units is not None else '--')}</span><span>Status: {esc('active compounding inventory' if status == 'holding_active_inventory' else status.replace('_',' '))}</span><span>Source: wallet truth</span></div></div>'''

        derived_events = []
        if status == 'holding_active_inventory':
            derived_events.append({'title': 'Active inventory detected', 'created_at': updated_at, 'event_type': 'inventory', 'severity': 'info'})
        if persistence == 'postgresql':
            derived_events.append({'title': 'PostgreSQL persistence live', 'created_at': updated_at, 'event_type': 'persistence', 'severity': 'info'})
        merged_events = (events or [])[:8] or derived_events
        events_html = ''.join([
            f'''<div class="activity-row"><div class="activity-top"><div>{esc(row.get('title'))}</div><div>{esc(row.get('created_at'))}</div></div><div class="meta-row"><span>{esc((row.get('event_type') or '').replace('_',' '))}</span><span>{esc(row.get('severity'))}</span></div></div>'''
            for row in merged_events
        ]) or '<div class="activity-empty">No recent HQ events available.</div>'

        if next_actions_data:
            next_actions_html = ''.join(
                f'<div class="next-action"><div class="num">{idx}</div><div class="action-copy"><strong>{esc(item.get("title") or "Action")}</strong>{esc(item.get("detail") or "")}</div></div>'
                for idx, item in enumerate(next_actions_data, start=1)
            )
        else:
            next_actions_html = (
                f'''<div class="next-action"><div class="num">1</div><div class="action-copy"><strong>Supervise active hold</strong>Track {esc(holding_asset)} exposure and recycle path.</div></div>
<div class="next-action"><div class="num">2</div><div class="action-copy"><strong>Verify mark and units</strong>Confirm {esc(holding_units if holding_units is not None else '--')} units and {money(invested)} invested.</div></div>
<div class="next-action"><div class="num">3</div><div class="action-copy"><strong>Do not force new entry</strong>Compounding capital is deployed, not missing.</div></div>'''
                if status == 'holding_active_inventory' else
                '''<div class="next-action"><div class="num">1</div><div class="action-copy"><strong>Verify funded readiness</strong>Confirm deployable cash and runtime health before any new entry.</div></div>
<div class="next-action"><div class="num">2</div><div class="action-copy"><strong>Wait for valid edge</strong>No forced trade until signal quality clears mandate.</div></div>
<div class="next-action"><div class="num">3</div><div class="action-copy"><strong>Preserve capital discipline</strong>Stay flat until setup quality is real.</div></div>'''
            )

        war_room_html = (ROOT / 'dashboard' / 'public' / 'war-room' / 'index.html').read_text()
        war_room_style = war_room_html.split('<style>', 1)[1].split('</style>', 1)[0]

        hq_lesson_copy = "Yesterday's lesson: the old dashboard kept drifting into disconnected UI, stale routes, and runtime mismatch. HQ now stays decision-first, with SQL called out explicitly and legacy UI isolated behind /legacy."
        action_banner_html = f'''<section class="card section" style="border:1px solid rgba(239,68,68,0.45); background:rgba(127,29,29,0.24);"><div class="section-head"><div><div class="section-title">Action required</div><div class="section-sub">Inactivity is now a surfaced failure state</div></div></div><div class="blocker"><strong>Both engines are stale.</strong> Tradier freshness: {esc(age_label(tradier_age))}. Bloc freshness: {esc(age_label(bloc_age))}. Realized actions today: {esc(str(scoreboard.get('realized_actions_today', 0)))}.</div></section>''' if action_required else ''
        compact_style = '''<style>body{margin:0;padding:0;background:#05070b;color:#edf4ff;font-family:Inter,sans-serif;overflow:hidden}.shell{height:100vh;display:grid;grid-template-rows:84px 1fr;padding:12px;gap:12px;background:radial-gradient(circle at top,#17304f 0%,#08111b 34%,#05070b 70%)}.topbar{display:grid;grid-template-columns:1.25fr 1fr .95fr;gap:12px}.topcard,.mode-rail,.workspace,.drawer,.subpanel{background:linear-gradient(180deg,rgba(16,23,34,.96),rgba(8,12,18,.98));border:1px solid rgba(54,78,110,.55);border-radius:20px;box-shadow:0 18px 50px rgba(0,0,0,.38)}.topcard{display:flex;align-items:center;justify-content:space-between;padding:14px 18px}.brand-k{font-size:10px;letter-spacing:.22em;text-transform:uppercase;color:#f8b84e;font-weight:800}.brand-v{font-size:28px;font-weight:800;line-height:1}.brand-s{font-size:12px;color:#93a9c7;margin-top:4px}.status-strip{display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end}.pill{display:inline-flex;align-items:center;gap:8px;padding:9px 12px;border-radius:999px;background:#0c1522;border:1px solid #2a3f5c;font-size:11px;font-weight:700;color:#e3eefc}.shell-body{display:grid;grid-template-columns:88px 1fr 360px;gap:12px;min-height:0}.mode-rail{padding:12px;display:grid;grid-template-rows:auto 1fr auto;gap:12px;background:linear-gradient(180deg,#0d1420,#091019)}.mode-stack,.quick-stack{display:grid;gap:10px}.railbtn,.quickbtn,.toolbtn,.tabbtn{border:1px solid #2a3f5c;background:linear-gradient(180deg,#111a29,#0c131d);color:#edf4ff;border-radius:16px;cursor:pointer;transition:all .15s ease;font-weight:700}.railbtn{height:62px;font-size:10px;letter-spacing:.14em;text-transform:uppercase}.railbtn.active,.tabbtn.active,.quickbtn.active{border-color:#5ac8fa;background:linear-gradient(180deg,#18395a,#112336);box-shadow:0 14px 28px rgba(0,0,0,.32)}.workspace{display:grid;grid-template-rows:auto 1fr;min-height:0;overflow:hidden}.workspace-head{display:flex;justify-content:space-between;align-items:center;padding:14px 18px;border-bottom:1px solid rgba(73,95,124,.35)}.workspace-title{font-size:13px;letter-spacing:.18em;text-transform:uppercase;color:#d7e3f4;font-weight:800}.workspace-sub{font-size:11px;color:#8297b3}.workspace-main{padding:14px;display:grid;grid-template-rows:auto auto 1fr;gap:12px;min-height:0}.hero-grid{display:grid;grid-template-columns:1.35fr .85fr;gap:12px}.directive{padding:24px;border-radius:20px;background:linear-gradient(135deg,rgba(69,170,255,.18),rgba(11,19,29,.95));border:1px solid rgba(90,200,250,.24);box-shadow:inset 0 1px 0 rgba(255,255,255,.03)}.directive-k{font-size:10px;letter-spacing:.18em;text-transform:uppercase;color:#8dd9ff;margin-bottom:10px;font-weight:800}.directive-v{font-size:38px;font-weight:800;line-height:1.02;max-width:16ch}.directive-p{font-size:14px;color:#a5b7cf;margin-top:10px;max-width:68ch}.hero-side{display:grid;gap:12px}.action-banner{padding:16px;border-radius:18px;background:linear-gradient(180deg,#3a171c,#191015);border:1px solid #7c3342;color:#ffd6db;font-size:12px;font-weight:700}.mini-metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}.metric{padding:14px;border-radius:16px;background:linear-gradient(180deg,#0f1825,#0b1119);border:1px solid #1f2f45}.metric-k{font-size:10px;letter-spacing:.14em;text-transform:uppercase;color:#8297b3}.metric-v{font-size:22px;font-weight:800;margin-top:6px}.metric-s{font-size:11px;color:#9fb2cc;margin-top:4px}.view-tabs{display:flex;gap:8px;flex-wrap:wrap}.tabbtn,.quickbtn,.toolbtn{padding:11px 14px;font-size:12px}.toolbtn{background:linear-gradient(180deg,#13263b,#0f1824);border-color:#2f4b6d}.toolbtn.danger{border-color:#7c3342;background:linear-gradient(180deg,#32151a,#1b1014);color:#ffd6db}.toolbtn.busy{opacity:.6;pointer-events:none}.view-pane{display:none;min-height:0}.view-pane.active{display:grid}.overview-grid{display:grid;grid-template-columns:1.08fr .92fr;gap:12px;min-height:0}.subpanel{display:flex;flex-direction:column;min-height:0}.subpanel-head{display:flex;justify-content:space-between;align-items:center;padding:12px 14px;border-bottom:1px solid rgba(73,95,124,.35)}.subpanel-title{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:#d8e3f5;font-weight:800}.subpanel-sub{font-size:10px;color:#7f95b2}.subpanel-body{padding:14px;min-height:0;overflow:auto}.kv{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.kv div{padding:12px;border-radius:14px;background:#0c1521;border:1px solid #1c2a3d}.kv span{display:block;font-size:10px;color:#7f95b2;margin-bottom:5px}.list{display:grid;gap:10px}.list-item{padding:12px;border-radius:14px;background:#0c1521;border:1px solid #1c2a3d}.compact-pre{white-space:pre-wrap;overflow:auto;background:#081019;padding:12px;border-radius:14px;border:1px solid #24354c;font-size:10px;max-height:260px}.drawer{display:grid;grid-template-rows:auto auto 1fr;gap:12px;padding:12px;min-height:0;background:linear-gradient(180deg,#0c1420,#081019)}.drawer-card{background:#0d1521;border:1px solid #1d2d42;border-radius:18px;display:flex;flex-direction:column;min-height:0}.drawer-head{display:flex;justify-content:space-between;align-items:center;padding:12px 14px;border-bottom:1px solid rgba(73,95,124,.35)}.drawer-body{padding:14px;min-height:0;overflow:auto}.statusline,.micro{font-size:11px;color:#91a6c1}.slim-input,.slim-textarea{width:100%;background:#081019;color:#edf4ff;border:1px solid #29405d;border-radius:14px;padding:11px}.slim-textarea{min-height:160px;font-family:'JetBrains Mono',monospace;font-size:11px}.toolbar{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:12px}.footer-note{padding-top:10px;font-size:10px;color:#7f95b2}.hide{display:none}.scroll{overflow:auto;min-height:0}@media (max-width:1280px){body{overflow:auto}.shell{height:auto}.topbar,.shell-body,.hero-grid,.overview-grid,.mini-metrics,.toolbar,.kv{grid-template-columns:1fr}.shell-body{grid-template-columns:1fr}.mode-rail{grid-template-columns:repeat(3,1fr);grid-template-rows:auto}.mode-stack,.quick-stack{grid-template-columns:repeat(3,1fr)}}@media (max-width:860px){.mode-rail{grid-template-columns:repeat(2,1fr)}.view-tabs,.status-strip{display:grid;grid-template-columns:1fr 1fr}}</style>'''
        controls_html = '''<button class="toolbtn" data-command="refresh_truth" data-label="Refresh" type="button" onclick="runCommand('refresh_truth')">Refresh</button><button class="toolbtn" data-command="diagnose_tradier" data-label="Tradier diag" type="button" onclick="runCommand('diagnose_tradier')">Tradier diag</button><button class="toolbtn" data-command="diagnose_bloc" data-label="Bloc diag" type="button" onclick="runCommand('diagnose_bloc')">Bloc diag</button><button class="toolbtn" data-command="pause_bloc" data-label="Pause Bloc" type="button" onclick="runCommand('pause_bloc')">Pause Bloc</button><button class="toolbtn" data-command="resume_bloc" data-label="Resume Bloc" type="button" onclick="runCommand('resume_bloc')">Resume Bloc</button><button class="toolbtn danger" data-command="close_all" data-label="Close all" type="button" onclick="runCommand('close_all')">Close all</button>'''
        command_console_html = '''<div class="drawer-card"><div class="drawer-head"><strong>Command console</strong><span class="pill">RUNNER</span></div><div class="drawer-body"><div class="toolbar">'''+controls_html+'''</div><div class="statusline" style="margin:10px 0 8px;">Type or tap an action, then watch the workspace update.</div><div class="slim-input" id="console-input" style="display:flex;align-items:center;justify-content:space-between;gap:8px;"><span style="opacity:.75;">></span><span id="console-preview" style="flex:1;color:#9fb3cc;">refresh_truth</span><button class="quickbtn" type="button" onclick="runConsoleCommand()">Run</button></div><div style="margin-top:10px;"><div class="subpanel-title" style="margin-bottom:6px;">Recent commands</div><pre id="recent-commands-box" class="compact-pre">--</pre></div></div></div>'''
        primary_action_html = f'''<div class="drawer-card"><div class="drawer-head"><strong>Primary next action</strong><span class="pill">NOW</span></div><div class="drawer-body"><div id="primary-action-title" style="font-size:18px;font-weight:800;line-height:1.1;margin-bottom:8px;">{esc((next_actions_data[0].get('title') if next_actions_data else 'Stabilize operator truth') if next_actions_data else 'Stabilize operator truth')}</div><div id="primary-action-detail" class="micro" style="margin-bottom:12px;">{esc((next_actions_data[0].get('detail') if next_actions_data else 'Force a fresh systems read, then act on the blocker.') if next_actions_data else 'Force a fresh systems read, then act on the blocker.')}</div><div class="toolbar"><button class="toolbtn" type="button" onclick="runCommand('refresh_truth')">Run primary action</button><button class="toolbtn" type="button" onclick="showView('overview')">Focus workspace</button></div><div id="primary-action-status" class="micro" style="margin-top:10px;">Awaiting operator input.</div></div></div>'''
        ops_tape_html = '''<div class="drawer-card"><div class="drawer-head"><strong>Operations tape</strong><span class="pill">LIVE</span></div><div class="drawer-body"><pre id="ops-tape-box" class="compact-pre">--</pre></div></div>'''
        notes_html = '''<div class="panel"><div class="panel-head"><div><div class="panel-title">Operator note</div><div class="panel-sub">Quick note, quick save</div></div></div><div class="notes-wrap"><textarea id="hq-note-input" class="slim-input" style="min-height:80px;"></textarea><div class="toolbar"><button class="toolbtn" type="button" onclick="saveNote()">Save note</button><button class="toolbtn" type="button" onclick="loadOverview()">Reload</button></div><div id="note-status" class="micro">No note saved yet.</div></div></div>'''
        config_html = '''<div class="panel"><div class="panel-head"><div><div class="panel-title">Safety config</div><div class="panel-sub">Edit limits directly</div></div></div><div class="config-wrap"><textarea id="hq-config-input" class="slim-textarea"></textarea><div class="toolbar"><button class="toolbtn" type="button" onclick="saveConfig()">Save config</button><button class="toolbtn" type="button" onclick="loadOverview()">Reload desk</button></div><div id="config-status" class="micro">Config not loaded yet.</div></div></div>'''
        logs_html = '''<div class="logs-wrap"><div class="dense-grid"><div class="dense-card"><h3>Refresh status</h3><pre id="refresh-status-box" class="compact-pre">--</pre></div><div class="dense-card"><h3>Action feedback</h3><pre id="action-feedback-box" class="compact-pre">--</pre></div><div class="dense-card"><h3>Recent notes</h3><pre id="notes-log-box" class="compact-pre"></pre></div><div class="dense-card"><h3>Signals</h3><pre id="signals-log-box" class="compact-pre"></pre></div><div class="dense-card"><h3>Trades/logs</h3><pre id="trades-log-box" class="compact-pre"></pre></div><div class="dense-card"><h3>Refresh log</h3><pre id="refresh-log-box" class="compact-pre"></pre></div></div></div>'''
        result_center_html = '''<div class="subpanel"><div class="subpanel-head"><div><div class="subpanel-title">Live result workspace</div><div class="subpanel-sub">What the last command or system action actually did</div></div><span class="pill">RESULT</span></div><div class="subpanel-body"><div class="directive" style="padding:12px;margin-bottom:10px;"><div class="directive-k">Latest result</div><div class="directive-v" id="latest-result-title" style="font-size:20px;">Waiting for action</div><div class="directive-p" id="latest-result-message">Run a command or inspect system output.</div></div><div class="overview-grid"><div class="drawer-card"><div class="drawer-head"><strong>Command response</strong></div><div class="drawer-body"><pre id="latest-result-json" class="compact-pre">--</pre></div></div><div class="drawer-card"><div class="drawer-head"><strong>System pulse</strong></div><div class="drawer-body"><pre id="recent-events-box" class="compact-pre">--</pre></div></div></div></div></div>'''
        scoreboard_html = f'''<section class="card section"><div class="section-head"><div><div class="section-title">Execution scoreboard</div><div class="section-sub">Today, not vibes</div></div></div><div class="ops-item"><div class="kv"><div><span>Tradier fills</span>{esc(scoreboard.get('tradier_fills_today', 0))}</div><div><span>Tradier previews</span>{esc(scoreboard.get('tradier_previews_today', 0))}</div><div><span>Bloc trades</span>{esc(scoreboard.get('bloc_trades_today', 0))}</div><div><span>Realized actions</span>{esc(scoreboard.get('realized_actions_today', 0))}</div><div><span>Tradier freshness</span>{esc(age_label(tradier_age))}</div><div><span>Bloc freshness</span>{esc(age_label(bloc_age))}</div></div></div></section>'''
        control_script = '''<script>(function(){ function setText(id, value){ var el=document.getElementById(id); if(el) el.textContent=value; } function pretty(value){ try { return JSON.stringify(value || {}, null, 2); } catch(err){ return String(value || ''); } } function commandToView(command){ if(!command) return 'overview'; if(command.indexOf('tradier') !== -1) return 'tradier'; if(command.indexOf('bloc') !== -1) return 'bloc'; if(command.indexOf('config') !== -1) return 'settings'; return 'overview'; } function setBusy(command, busy){ document.querySelectorAll('[data-command]').forEach(function(btn){ if(btn.getAttribute('data-command') === command){ btn.classList.toggle('busy', busy); btn.textContent = busy ? 'Running…' : btn.getAttribute('data-label'); } }); } function renderScene(name){ var host = document.getElementById('workspace-scene'); var tpl = document.getElementById('scene-' + name); if(!host || !tpl) return; host.innerHTML = ''; host.appendChild(tpl.content.cloneNode(true)); } function setLatestResult(data){ var latest = data && data.latest_result ? data.latest_result : null; var recent = data && data.recent_events ? data.recent_events : []; setText('latest-result-title', latest ? (latest.event_type || latest.kind || 'Latest event') : 'Waiting for action'); setText('latest-result-message', latest ? (latest.summary || latest.message || latest.details || 'No summary available') : 'Run a command or inspect system output.'); setText('latest-result-json', pretty(latest || {})); setText('recent-events-box', pretty(recent)); setText('recent-events-box-secondary', pretty(recent)); setText('ops-tape-box', recent.map(function(item){ return [item.created_at || item.timestamp || '--', item.event_type || item.kind || 'event', item.summary || item.message || ''].join(' | '); }).join('\\n') || '--'); setText('recent-commands-box', recent.slice(0,8).map(function(item){ return (item.event_type || item.kind || 'event') + ' :: ' + (item.summary || item.message || '--'); }).join('\\n') || '--'); setText('context-drawer-box', latest ? pretty(latest) : 'No live context selected yet.'); if(latest){ setText('primary-action-status', 'Last command: ' + (latest.summary || latest.message || latest.event_type || 'updated')); } } function showView(name){ document.querySelectorAll('[data-view]').forEach(function(btn){ btn.classList.toggle('active', btn.getAttribute('data-view') === name); }); document.querySelectorAll('.railbtn').forEach(function(btn){ btn.classList.toggle('active', (btn.textContent || '').trim().toLowerCase() === name); }); renderScene(name); setText('context-drawer-box', 'Context: ' + name + '\\n\\nUse the command console or workspace controls to operate this mode.'); } function setConsolePreview(command){ setText('console-preview', command || 'refresh_truth'); setText('primary-action-status', 'Console armed for ' + (command || 'refresh_truth')); } async function runCommand(command){ var targetView = commandToView(command); showView(targetView); setConsolePreview(command); setText('command-status', 'Running ' + command + '...'); setText('primary-action-status', 'Running ' + command + '...'); setBusy(command, true); setText('ops-tape-box', 'RUNNING | ' + command + '\\n' + ((document.getElementById('ops-tape-box') || {}).textContent || '')); setText('recent-commands-box', 'RUN ' + command + '\\n' + ((document.getElementById('recent-commands-box') || {}).textContent || '')); try { const res = await fetch('/api/command', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({command: command})}); const data = await res.json(); var message = data.message || data.error || ('Command ' + command + ' finished'); setText('command-status', message); setText('primary-action-title', 'Executed: ' + command); setText('primary-action-detail', message); setText('primary-action-status', res.ok ? 'Command completed.' : 'Command returned an error.'); setText('context-drawer-box', pretty(data)); setText('ops-tape-box', [new Date().toISOString(), command, message].join(' | ') + '\\n' + ((document.getElementById('ops-tape-box') || {}).textContent || '')); setText('recent-commands-box', command + ' :: ' + message + '\\n' + ((document.getElementById('recent-commands-box') || {}).textContent || '')); await loadOverview(); if(command === 'refresh_truth' && res.ok){ setTimeout(function(){ window.location.reload(); }, 900); } } catch(err){ setText('command-status', 'Command failed: ' + err.message); setText('primary-action-title', 'Command failed'); setText('primary-action-detail', err.message); setText('primary-action-status', 'Network or runtime failure.'); setText('context-drawer-box', err.stack || err.message); setText('ops-tape-box', [new Date().toISOString(), command, 'FAILED', err.message].join(' | ') + '\\n' + ((document.getElementById('ops-tape-box') || {}).textContent || '')); } finally { setBusy(command, false); } } function runConsoleCommand(){ var preview = document.getElementById('console-preview'); var command = preview && preview.textContent ? preview.textContent.trim() : 'refresh_truth'; runCommand(command); } async function loadOverview(){ try { const res = await fetch('/api/hq/overview', {cache:'no-store'}); const data = await res.json(); document.querySelectorAll('#hq-config-input').forEach(function(cfg){ cfg.value = JSON.stringify(data.safety_config || {}, null, 2); }); setText('refresh-status-box', pretty(data.refresh_status || {})); setText('action-feedback-box', pretty(data.action_feedback || {})); setText('notes-log-box', (data.notes || []).join('\\n')); setText('signals-log-box', (data.signals || []).join('\\n')); setText('trades-log-box', (data.trades || []).join('\\n')); setText('refresh-log-box', (data.refresh_log || []).join('\\n')); setLatestResult(data); setText('config-status', 'Config loaded'); } catch(err){ setText('config-status', 'Overview load failed: ' + err.message); setText('command-status', 'Overview load failed: ' + err.message); setText('primary-action-status', 'Overview load failed.'); } } async function saveNote(){ var input=document.getElementById('hq-note-input'); var note=(input && input.value ? input.value : '').trim(); if(!note){ setText('note-status', 'Note is empty'); return; } try { const res = await fetch('/api/hq/notes',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({note: note})}); const data = await res.json(); setText('note-status', data.message || data.error || 'Note saved'); setText('context-drawer-box', pretty(data)); setText('ops-tape-box', [new Date().toISOString(), 'save_note', data.message || 'Note saved'].join(' | ') + '\\n' + ((document.getElementById('ops-tape-box') || {}).textContent || '')); if(res.ok && input){ input.value=''; await loadOverview(); } } catch(err){ setText('note-status', 'Note save failed: ' + err.message); } } async function saveConfig(){ var raw=(document.getElementById('hq-config-input') || {}).value || ''; try { const parsed=JSON.parse(raw); const res=await fetch('/api/hq/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({config: parsed})}); const data=await res.json(); setText('config-status', data.message || data.error || 'Config saved'); setText('context-drawer-box', pretty(data)); setText('ops-tape-box', [new Date().toISOString(), 'save_config', data.message || 'Config saved'].join(' | ') + '\\n' + ((document.getElementById('ops-tape-box') || {}).textContent || '')); if(res.ok){ showView('settings'); await loadOverview(); } } catch(err){ setText('config-status', 'Config save failed: ' + err.message); } } function showTab(name){ document.querySelectorAll('.tabbtn[data-tab]').forEach(function(btn){ btn.classList.toggle('active', btn.getAttribute('data-tab') === name); }); document.querySelectorAll('.tabpane').forEach(function(pane){ pane.classList.toggle('active', pane.id === 'tab-' + name); }); } window.runCommand=runCommand; window.runConsoleCommand=runConsoleCommand; window.saveNote=saveNote; window.saveConfig=saveConfig; window.loadOverview=loadOverview; window.showTab=showTab; window.showView=showView; window.setConsolePreview=setConsolePreview; if(document.readyState === 'loading'){ document.addEventListener('DOMContentLoaded', function(){ showView('overview'); loadOverview(); }); } else { showView('overview'); loadOverview(); } })();</script>'''
        scoreboard_panel_html = f'''<div class="mini-stack"><div class="kv"><div><span>Tradier fills</span>{esc(scoreboard.get('tradier_fills_today', 0))}</div><div><span>Tradier previews</span>{esc(scoreboard.get('tradier_previews_today', 0))}</div><div><span>Bloc trades</span>{esc(scoreboard.get('bloc_trades_today', 0))}</div><div><span>Realized actions</span>{esc(scoreboard.get('realized_actions_today', 0))}</div><div><span>Tradier freshness</span>{esc(age_label(tradier_age))}</div><div><span>Bloc freshness</span>{esc(age_label(bloc_age))}</div></div></div>'''

        html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>HQ — Bazaar Operator Command Center</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
    {compact_style}
</head>
<body>
    <div class="shell">
        <section class="topbar">
            <div class="topcard">
                <div>
                    <div class="brand-k">Bazaar of Fortunes</div>
                    <div class="brand-v">Operator Cockpit</div>
                    <div class="brand-s">Command-first workspace for execution, diagnosis, and operator control.</div>
                </div>
                <div class="statusline">{esc(updated_at)} | {esc(payload.get('build'))}</div>
            </div>
            <div class="topcard">
                <div>
                    <div class="brand-k">Primary directive</div>
                    <div style="font-size:18px;font-weight:800;line-height:1.1;">{esc(primary_directive)}</div>
                </div>
            </div>
            <div class="topcard">
                <div class="status-strip">
                    <span class="pill">Tradier {esc(tradier_status)}</span>
                    <span class="pill">Bloc {esc('Active' if status == 'holding_active_inventory' else 'Idle')}</span>
                    <span class="pill">Tradier {esc(age_label(tradier_age))}</span>
                    <span class="pill">Bloc {esc(age_label(bloc_age))}</span>
                </div>
            </div>
        </section>
        <section class="shell-body">
            <aside class="mode-rail">
                <div class="mode-stack">
                    <button class="railbtn active" type="button" onclick="showView('overview')">Overview</button>
                    <button class="railbtn" type="button" onclick="showView('tradier')">Tradier</button>
                    <button class="railbtn" type="button" onclick="showView('bloc')">Bloc</button>
                    <button class="railbtn" type="button" onclick="showView('journal')">Journal</button>
                    <button class="railbtn" type="button" onclick="showView('logs')">Logs</button>
                    <button class="railbtn" type="button" onclick="showView('settings')">Settings</button>
                </div>
                <div></div>
                <div class="quick-stack">
                    <button class="quickbtn" type="button" data-command="refresh_truth" data-label="Refresh" onclick="setConsolePreview('refresh_truth');runCommand('refresh_truth')">Refresh</button>
                    <button class="quickbtn" type="button" data-command="diagnose_tradier" data-label="Tradier diag" onclick="setConsolePreview('diagnose_tradier');runCommand('diagnose_tradier')">T diag</button>
                    <button class="quickbtn" type="button" data-command="diagnose_bloc" data-label="Bloc diag" onclick="setConsolePreview('diagnose_bloc');runCommand('diagnose_bloc')">B diag</button>
                    <button class="quickbtn" type="button" data-command="pause_bloc" data-label="Pause Bloc" onclick="setConsolePreview('pause_bloc');runCommand('pause_bloc')">Pause</button>
                    <button class="quickbtn" type="button" data-command="resume_bloc" data-label="Resume Bloc" onclick="setConsolePreview('resume_bloc');runCommand('resume_bloc')">Resume</button>
                    <button class="quickbtn" type="button" data-command="pause_tradier" data-label="Pause Tradier" onclick="setConsolePreview('pause_tradier');runCommand('pause_tradier')">T pause</button>
                    <button class="quickbtn active" type="button" data-command="close_all" data-label="Close all" onclick="setConsolePreview('close_all');runCommand('close_all')">Close</button>
                </div>
            </aside>
            <main class="workspace">
                <div class="workspace-head">
                    <div>
                        <div class="workspace-title">Central workspace</div>
                        <div class="workspace-sub">Operate by mode, not by scrolling a report</div>
                    </div>
                    <div class="statusline" id="command-status">No command run yet.</div>
                </div>
                <div class="workspace-main">
                    <div id="workspace-scene"></div>
                    <template id="scene-overview"><div style="display:grid;gap:14px;"><div class="overview-grid" style="grid-template-columns:1.28fr .72fr;"><div class="directive"><div class="directive-k">Operator directive</div><div class="directive-v">{esc(primary_directive)}</div><div class="directive-p">{esc(operator_summary)}</div><div class="toolbar" style="margin-top:18px;"><button class="toolbtn" type="button" onclick="runCommand('diagnose_tradier')">Diagnose Tradier</button><button class="toolbtn" type="button" onclick="runCommand('diagnose_bloc')">Diagnose Bloc</button><button class="toolbtn" type="button" onclick="runCommand('refresh_truth')">Refresh truth</button><button class="toolbtn danger" type="button" onclick="runCommand('close_all')">Emergency close</button></div><div class="mini-metrics" style="margin-top:18px;"><div class="metric"><div class="metric-k">Tradier</div><div class="metric-v">{esc(tradier_status)}</div><div class="metric-s">{esc((money(tradier_buying_power) + ' ready') if tradier_status == 'Ready' else (tradier.get('top_blocker') or 'blocked'))}</div></div><div class="metric"><div class="metric-k">Bloc</div><div class="metric-v">{esc('Active' if status == 'holding_active_inventory' else 'Idle')}</div><div class="metric-s">{esc(holding_asset + ' ' + str(holding_units) if status == 'holding_active_inventory' and holding_asset else money(deployable) + ' deployable')}</div></div><div class="metric"><div class="metric-k">Tradier freshness</div><div class="metric-v">{esc(age_label(tradier_age))}</div><div class="metric-s">{money(tradier_buying_power)}</div></div><div class="metric"><div class="metric-k">Bloc freshness</div><div class="metric-v">{esc(age_label(bloc_age))}</div><div class="metric-s">{esc(reality_feed)}</div></div></div></div><div class="subpanel"><div class="subpanel-head"><div><div class="subpanel-title">Command rail</div><div class="subpanel-sub">Immediate operator lane</div></div><span class="pill">LIVE</span></div><div class="subpanel-body">{'<div class="action-banner" style="margin-bottom:12px;">Both engines are stale. Tradier freshness: ' + esc(age_label(tradier_age)) + '. Bloc freshness: ' + esc(age_label(bloc_age)) + '. Realized actions today: ' + esc(str(scoreboard.get('realized_actions_today', 0))) + '.</div>' if action_required else '<div class="action-banner" style="margin-bottom:12px;background:linear-gradient(180deg,#163322,#0d1812);border-color:#2d7047;color:#d5ffe2;">Systems visible. No immediate operator emergency flagged.</div>'}<div class="list">{next_actions_html}</div><div class="drawer-card" style="margin-top:12px;"><div class="drawer-head"><strong>Latest result</strong><span class="pill">RESULT</span></div><div class="drawer-body"><div id="latest-result-title" style="font-size:24px;font-weight:800;line-height:1.05;margin-bottom:8px;">Waiting for action</div><div id="latest-result-message" class="micro" style="margin-bottom:12px;">Run a command or inspect system output.</div><pre id="latest-result-json" class="compact-pre">--</pre></div></div></div></div></div><div class="overview-grid" style="grid-template-columns:.95fr 1.05fr;"><div class="subpanel"><div class="subpanel-head"><div><div class="subpanel-title">Operator blockers</div><div class="subpanel-sub">What is stopping real trading right now</div></div></div><span class="pill">FOCUS</span></div><div class="subpanel-body"><div class="list"><div class="list-item"><strong>Tradier blocker</strong><div class="micro" style="margin-top:6px;">{esc('Execution is stale despite account readiness. Last real action path needs validation.')}</div></div><div class="list-item"><strong>Bloc blocker</strong><div class="micro" style="margin-top:6px;">{esc('Inventory is live but not cycling. Wallet truth, execution path, and recycle logic need hands-on supervision.')}</div></div><div class="list-item"><strong>Operator posture</strong><div class="micro" style="margin-top:6px;">{esc('Use this page as the desk: diagnose, inspect logs, edit configs, then verify behavior before trusting automation.')}</div></div></div></div></div><div class="subpanel"><div class="subpanel-head"><div><div class="subpanel-title">System pulse</div><div class="subpanel-sub">Command output and event trail</div></div><span class="pill">PULSE</span></div><div class="subpanel-body"><div class="overview-grid"><div class="drawer-card"><div class="drawer-head"><strong>Command response</strong></div><div class="drawer-body"><pre id="recent-events-box" class="compact-pre">--</pre></div></div><div class="drawer-card"><div class="drawer-head"><strong>Operations tape</strong></div><div class="drawer-body"><pre id="ops-tape-box" class="compact-pre">--</pre></div></div></div></div></div></div><div class="overview-grid"><div class="subpanel"><div class="subpanel-head"><div><div class="subpanel-title">Engine truth</div><div class="subpanel-sub">Readiness and exposure</div></div></div><div class="subpanel-body"><div class="kv"><div><span>Tradier status</span>{esc(tradier_status)}</div><div><span>Buying power</span>{money(tradier_buying_power)}</div><div><span>Tradier freshness</span>{esc(age_label(tradier_age))}</div><div><span>Bloc state</span>{esc(status)}</div><div><span>Holding</span>{esc(holding_asset + (' ' + str(holding_units) if holding_units is not None and holding_asset else ''))}</div><div><span>Deployable</span>{money(deployable)}</div></div><div class="footer-note">{esc(hq_lesson_copy)}</div></div></div><div class="subpanel"><div class="subpanel-head"><div><div class="subpanel-title">Quick audit surfaces</div><div class="subpanel-sub">Immediate live artifacts</div></div></div><div class="subpanel-body"><div class="drawer-card" style="margin-bottom:12px;"><div class="drawer-head"><strong>Tradier board</strong><span class="pill">LIVE</span></div><div class="drawer-body"><pre class="compact-pre">{esc(tradier_board_text[:1200])}</pre></div></div><div class="drawer-card"><div class="drawer-head"><strong>Bloc wallet truth</strong><span class="pill">LIVE</span></div><div class="drawer-body"><pre class="compact-pre">{esc(bloc_wallet_text[:1200])}</pre></div></div></div></div></div></div></template>
                    <template id="scene-tradier"><div class="overview-grid"><div class="subpanel"><div class="subpanel-head"><div><div class="subpanel-title">Tradier workstation</div><div class="subpanel-sub">Readiness, blocker, execution lane, and candidate review</div></div></div><div class="subpanel-body"><div class="kv"><div><span>Status</span>{esc(tradier_status)}</div><div><span>Buying power</span>{money(tradier_buying_power)}</div><div><span>Freshness</span>{esc(age_label(tradier_age))}</div><div><span>Top blocker</span>{esc(tradier.get('top_blocker') or 'None visible')}</div><div><span>Ready flag</span>{esc('yes' if tradier.get('ready') else 'no')}</div><div><span>Open positions</span>{esc(tradier.get('positions_count') or 0)}</div></div><div class="toolbar"><button class="toolbtn" type="button" data-command="diagnose_tradier" data-label="Tradier diag" onclick="runCommand('diagnose_tradier')">Run Tradier diagnostic</button><button class="toolbtn" type="button" data-command="refresh_truth" data-label="Refresh" onclick="runCommand('refresh_truth')">Refresh board</button><button class="toolbtn" type="button" data-command="pause_tradier" data-label="Pause Tradier" onclick="runCommand('pause_tradier')">Pause Tradier</button><button class="toolbtn danger" type="button" data-command="close_all" data-label="Close all" onclick="runCommand('close_all')">Emergency close</button></div><div class="footer-note">Execution from HQ is now candidate-first: inspect board, blocker, audit trail, and risk config from one place.</div><div style="margin-top:12px;">{result_center_html}</div></div></div><div class="subpanel"><div class="subpanel-head"><div><div class="subpanel-title">Tradier execution lane</div><div class="subpanel-sub">Board, audit trail, and editable risk surface</div></div></div><div class="subpanel-body"><div class="drawer-card" style="margin-bottom:10px;"><div class="drawer-head"><strong>Leaders board</strong><span class="pill">LIVE</span></div><div class="drawer-body"><pre id="tradier-board-box" class="compact-pre">{esc(tradier_board_text)}</pre></div></div><div class="drawer-card" style="margin-bottom:10px;"><div class="drawer-head"><strong>Execution audit</strong><span class="pill">LOG</span></div><div class="drawer-body"><pre id="tradier-audit-box" class="compact-pre">{esc(chr(10).join(tradier_audit_lines) if tradier_audit_lines else '--')}</pre></div></div><div class="drawer-card"><div class="drawer-head"><strong>Risk / execution config</strong><span class="pill">EDIT</span></div><div class="drawer-body"><textarea id="tradier-risk-input" class="slim-textarea">{esc(risk_config_text)}</textarea><div class="toolbar"><button class="toolbtn" type="button" onclick="saveConfigFromEditor('tradier-risk-input')">Save HQ config</button><button class="toolbtn" type="button" onclick="loadOverview()">Reload desk</button></div><div class="footer-note">Use this to stage risk and exit-condition edits before tomorrow's open.</div></div></div></div></div></template>
                    <template id="scene-bloc"><div class="overview-grid"><div class="subpanel"><div class="subpanel-head"><div><div class="subpanel-title">Bloc workstation</div><div class="subpanel-sub">Runtime, inventory, wallet truth, and intervention</div></div></div><div class="subpanel-body"><div class="kv"><div><span>Status</span>{esc(status)}</div><div><span>Deployable</span>{money(deployable)}</div><div><span>Holding</span>{esc(holding_asset + (' ' + str(holding_units) if holding_units is not None and holding_asset else ''))}</div><div><span>Feed</span>{esc(reality_feed)}</div><div><span>Trades today</span>{esc(scoreboard.get('bloc_trades_today') or 0)}</div><div><span>Inventory EV</span>{money(invested)}</div></div><div class="toolbar"><button class="toolbtn" type="button" data-command="diagnose_bloc" data-label="Bloc diag" onclick="runCommand('diagnose_bloc')">Run Bloc diagnostic</button><button class="toolbtn" type="button" data-command="pause_bloc" data-label="Pause Bloc" onclick="runCommand('pause_bloc')">Pause Bloc</button><button class="toolbtn" type="button" data-command="resume_bloc" data-label="Resume Bloc" onclick="runCommand('resume_bloc')">Resume Bloc</button><button class="toolbtn" type="button" data-command="refresh_truth" data-label="Refresh" onclick="runCommand('refresh_truth')">Refresh wallet truth</button></div><div style="margin-top:12px;">{result_center_html}</div></div></div><div class="subpanel"><div class="subpanel-head"><div><div><div class="subpanel-title">Bloc control lane</div><div class="subpanel-sub">Wallet, state, and editable operator config</div></div></div></div><div class="subpanel-body"><div class="drawer-card" style="margin-bottom:10px;"><div class="drawer-head"><strong>Wallet truth</strong><span class="pill">LIVE</span></div><div class="drawer-body"><pre id="bloc-wallet-box" class="compact-pre">{esc(bloc_wallet_text)}</pre></div></div><div class="drawer-card" style="margin-bottom:10px;"><div class="drawer-head"><strong>Runtime state</strong><span class="pill">LIVE</span></div><div class="drawer-body"><pre id="bloc-state-box" class="compact-pre">{esc(bloc_state_text)}</pre></div></div><div class="drawer-card"><div class="drawer-head"><strong>HQ safety config</strong><span class="pill">EDIT</span></div><div class="drawer-body"><textarea id="bloc-safety-input" class="slim-textarea">{esc(hq_safety_text)}</textarea><div class="toolbar"><button class="toolbtn" type="button" onclick="saveConfigFromEditor('bloc-safety-input')">Save HQ config</button><button class="toolbtn" type="button" onclick="loadOverview()">Reload desk</button></div><div class="footer-note">Edit hands-on intervention settings here while the bot is under supervision.</div></div></div></div></div></template>
                    <template id="scene-journal"><div class="overview-grid"><div class="subpanel"><div class="subpanel-head"><div><div class="subpanel-title">Operator notes</div><div class="subpanel-sub">Write it down</div></div></div><div class="subpanel-body">{notes_html}</div></div><div class="subpanel"><div class="subpanel-head"><div><div class="subpanel-title">Positions and activity</div><div class="subpanel-sub">Trail and review</div></div></div><div class="subpanel-body"><div class="view-tabs"><button class="tabbtn active" type="button" data-tab="positions" onclick="showTab('positions')">Positions</button><button class="tabbtn" type="button" data-tab="activity" onclick="showTab('activity')">Activity</button></div><div id="tab-positions" class="tabpane active"><div class="list">{positions_html}</div></div><div id="tab-activity" class="tabpane"><div class="list">{events_html}</div></div></div></div></div></template>
                    <template id="scene-logs"><div class="overview-grid"><div class="subpanel"><div class="subpanel-head"><div><div class="subpanel-title">System logs</div><div class="subpanel-sub">Signals, trades, refresh</div></div></div><div class="subpanel-body">{logs_html}</div></div><div class="subpanel"><div class="subpanel-head"><div><div class="subpanel-title">Recent pulse</div><div class="subpanel-sub">Event stream</div></div></div><div class="subpanel-body"><pre id="recent-events-box-secondary" class="compact-pre">--</pre></div></div></div></template>
                    <template id="scene-settings"><div class="overview-grid"><div class="subpanel"><div class="subpanel-head"><div><div class="subpanel-title">Safety config</div><div class="subpanel-sub">Risk and operating limits</div></div></div><div class="subpanel-body">{config_html}</div></div><div class="subpanel"><div class="subpanel-head"><div><div class="subpanel-title">Execution stats</div><div class="subpanel-sub">Today, not vibes</div></div></div><div class="subpanel-body">{scoreboard_panel_html}</div></div></div></template>
                </div>
            </main>
            <aside class="drawer">
                {primary_action_html}
                {command_console_html}
                {ops_tape_html}
                <div class="drawer-card" id="context-drawer"><div class="drawer-head"><strong>Context drawer</strong><span class="pill">FOCUS</span></div><div class="drawer-body"><pre id="context-drawer-box" class="compact-pre">Select a mode or run a command. Context will appear here.</pre></div></div>
            </aside>
        </section>
    </div>
    {control_script}
</body>
</html>'''
        return self.html_response(200, html)

    def _handle_eth_scalper_trades(self):
        """Get recent trades"""
        try:
            trades_file = ROOT / 'eth_scalper' / 'logs' / 'trades.jsonl'
            trades = []
            if trades_file.exists():
                with open(trades_file) as f:
                    for line in f.readlines()[-50:]:  # Last 50 trades
                        try:
                            entry = json.loads(line)
                            if entry.get('type') == 'trade':
                                trades.append(entry.get('data', {}))
                        except:
                            pass
            return self.json_response(200, {'trades': trades})
        except Exception as e:
            return self.json_response(500, {'ok': False, 'error': str(e)})

    def _handle_eth_scalper_positions(self):
        """Get open positions"""
        try:
            positions_file = ROOT / 'eth_scalper' / 'state' / 'positions.json'
            state_file = ROOT / 'eth_scalper' / 'state' / 'bot_state.json'
            wallet_file = ROOT / 'eth_scalper' / 'state' / 'wallet.json'
            if positions_file.exists():
                positions = json.loads(positions_file.read_text())
            else:
                positions = {'positions': []}
            pos_list = positions.get('positions', []) if isinstance(positions, dict) else []
            state = json.loads(state_file.read_text()) if state_file.exists() else {}
            wallet = json.loads(wallet_file.read_text()) if wallet_file.exists() else {}
            reconciled_positions = state.get('reconciled_positions') or []
            if not pos_list and reconciled_positions:
                synthetic = []
                for pos in reconciled_positions:
                    units = float(pos.get('allocated_units') or pos.get('binding_units') or pos.get('lot_units') or 0.0)
                    asset = str(pos.get('binding_asset') or pos.get('asset') or '').upper()
                    mark = None
                    if asset == 'CBBTC':
                        mark = float(wallet.get('cbbtc_price_usd', wallet.get('btc_price_usd', 0.0)) or 0.0)
                    elif asset == 'WETH':
                        mark = float(wallet.get('eth_price_usd') or 0.0)
                    synthetic.append({
                        'symbol': asset or 'INVENTORY',
                        'side': 'Hold',
                        'entry_price': pos.get('entry_price'),
                        'current_price': mark,
                        'pnl': None,
                        'status': pos.get('status') or 'holding_active_inventory',
                        'size': units,
                        'size_usd': round(units * mark, 2) if mark and units else None,
                    })
                pos_list = synthetic
            return self.json_response(200, {'positions': pos_list})
        except Exception as e:
            return self.json_response(500, {'ok': False, 'error': str(e)})

    def _handle_eth_scalper_signals(self):
        """Get signal history"""
        try:
            signals_file = ROOT / 'eth_scalper' / 'logs' / 'trades.jsonl'
            signals = []
            if signals_file.exists():
                with open(signals_file) as f:
                    for line in f.readlines()[-50:]:
                        try:
                            entry = json.loads(line)
                            if entry.get('type') == 'signal':
                                signals.append(entry.get('data', {}))
                        except:
                            pass
            return self.json_response(200, {'signals': signals})
        except Exception as e:
            return self.json_response(500, {'ok': False, 'error': str(e)})

    def _handle_eth_scalper_wallet(self):
        """Get wallet balances from Alchemy"""
        try:
            import sys
            sys.path.insert(0, str(ROOT / 'eth_scalper'))
            from wallet_monitor import wallet_monitor
            
            balances = wallet_monitor.get_all_balances()
            return self.json_response(200, balances)
        except Exception as e:
            # Fallback to state file if available
            try:
                state_file = ROOT / 'eth_scalper' / 'state' / 'wallet.json'
                if state_file.exists():
                    return self.json_response(200, json.loads(state_file.read_text()))
            except:
                pass
            return self.json_response(500, {'ok': False, 'error': str(e)})

    def _handle_eth_scalper_command(self, body):
        """Handle bot commands (STOP, START, etc.)"""
        try:
            payload = json.loads(body.decode() or '{}')
            command = payload.get('command', '').upper()
            
            # Write command to file for bot to pick up
            cmd_file = ROOT / 'eth_scalper' / 'state' / 'command.txt'
            cmd_file.parent.mkdir(parents=True, exist_ok=True)
            cmd_file.write_text(command)
            
            return self.json_response(200, {
                'ok': True,
                'command': command,
                'message': f'Command {command} queued'
            })
        except Exception as e:
            return self.json_response(500, {'ok': False, 'error': str(e)})

    def _serve_eth_scalper_logs(self):
        """Serve ETH scalper logs"""
        try:
            # Get the last 100 lines from journalctl
            result = subprocess.run(
                ['journalctl', '-u', 'eth-scalper', '-n', '100', '--no-pager'],
                capture_output=True,
                text=True
            )
            
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(result.stdout.encode())
        except Exception as e:
            self.json_response(500, {'ok': False, 'error': str(e)})


    def _handle_tradier_status(self):
        try:
            from tradier_account import readiness_snapshot
            from tradier_broker_interface import positions, list_orders
            snapshot = readiness_snapshot()
            pos = positions()
            ords = list_orders()
            # Determine health
            health = 'green' if snapshot.get('ready_for_options_execution') else 'red'
            # Buying power
            bp = snapshot.get('option_buying_power', 0.0)
            # Positions count
            if isinstance(pos, dict) and 'positions' in pos:
                if pos['positions'] == 'null':
                    pos_count = 0
                elif isinstance(pos['positions'], list):
                    pos_count = len(pos['positions'])
                elif isinstance(pos['positions'], dict):
                    # Single position wrapped in dict with key 'position'
                    pos_count = 1
                else:
                    pos_count = 0
            elif isinstance(pos, list):
                pos_count = len(pos)
            else:
                pos_count = 0
            # Orders count
            if isinstance(ords, dict) and 'orders' in ords:
                orders_data = ords['orders']
                if isinstance(orders_data, dict) and 'order' in orders_data:
                    order_item = orders_data['order']
                    if isinstance(order_item, list):
                        ord_count = len(order_item)
                    elif isinstance(order_item, dict):
                        ord_count = 1
                    else:
                        ord_count = 0
                else:
                    ord_count = 0
            elif isinstance(ords, list):
                ord_count = len(ords)
            else:
                ord_count = 0
            return self.json_response(200, {
                'bp': bp,
                'positions': pos_count,
                'orders': ord_count,
                'health': health
            })
        except Exception as e:
            # Fallback to placeholder
            return self.json_response(200, {
                'bp': 0.0,
                'positions': 0,
                'orders': 0,
                'health': 'red'
            })

    def _handle_sie_status(self):
        """Get SIE (LIE) status: order ID, ETH price, momentum"""
        try:
            import json, re, subprocess
            from datetime import datetime, timezone
            
            # Default values
            order_id = '121832076'
            eth_price = 0.0
            momentum = 0.0
            quote_id = None
            
            # Read LIE log
            log_path = ROOT / 'lie' / 'lie.log'
            if log_path.exists():
                log_content = log_path.read_text()
                lines = log_content.strip().split('\n')
                # Look for latest ETH price line
                for line in reversed(lines):
                    if 'ETH price:' in line:
                        match = re.search(r'\$([0-9]+\.?[0-9]*)', line)
                        if match:
                            eth_price = float(match.group(1))
                            break
                # Look for momentum or volatility signal
                for line in reversed(lines):
                    if 'momentum' in line.lower() or 'volatility' in line.lower():
                        # Try to extract percentage
                        match = re.search(r'([0-9]+\.?[0-9]*)%', line)
                        if match:
                            momentum = float(match.group(1))
                            break
                # Look for QuoteID
                for line in reversed(lines):
                    if 'QuoteID' in line:
                        match = re.search(r'QuoteID:\s*([^\s]+)', line)
                        if match:
                            quote_id = match.group(1)
                            break
            
            # Get current ETH price from CoinGecko as fallback
            if eth_price == 0.0:
                try:
                    import requests
                    resp = requests.get('https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd', timeout=5)
                    if resp.status_code == 200:
                        data = resp.json()
                        eth_price = data.get('ethereum', {}).get('usd', 0.0)
                except Exception:
                    pass
            
            return self.json_response(200, {
                'order_id': order_id,
                'eth_price': eth_price,
                'momentum': momentum,
                'quote_id': quote_id,
                'updated_at': datetime.now(timezone.utc).isoformat()
            })
        except Exception as e:
            # Fallback
            return self.json_response(200, {
                'order_id': '121832076',
                'eth_price': 0.0,
                'momentum': 0.0,
                'quote_id': None,
                'updated_at': datetime.now(timezone.utc).isoformat(),
                'error': str(e)
            })

    def _handle_bloc_status(self):
        try:
            import json
            wallet_path = ROOT / 'eth_scalper' / 'state' / 'wallet.json'
            positions_path = ROOT / 'eth_scalper' / 'state' / 'positions.json'
            state_path = ROOT / 'eth_scalper' / 'state' / 'bot_state.json'
            wallet = json.loads(wallet_path.read_text()) if wallet_path.exists() else {}
            positions_data = json.loads(positions_path.read_text()) if positions_path.exists() else {}
            bot_state = json.loads(state_path.read_text()) if state_path.exists() else {}
            usdc = float(wallet.get('usdc', 0.0) or 0.0)
            eth = float(wallet.get('eth', 0.0) or 0.0)
            weth = float(wallet.get('weth', 0.0) or 0.0)
            cbbtc = float(wallet.get('cbbtc', 0.0) or 0.0)
            btc_price = float(wallet.get('cbbtc_price_usd', wallet.get('btc_price_usd', 0.0)) or 0.0)
            eth_price = float(wallet.get('eth_price_usd', 0.0) or 0.0)
            pos_list = positions_data.get('positions', []) if isinstance(positions_data, dict) else []
            reconciled_positions = bot_state.get('reconciled_positions') or []
            active_positions = len(pos_list) if pos_list else (1 if reconciled_positions else 0)
            invested_capital = float(((bot_state.get('live_inventory') or {}).get('invested_capital_usd')) or 0.0)
            if invested_capital <= 0:
                invested_capital = (weth * eth_price) + (cbbtc * btc_price)
            holding_asset = 'CBBTC' if cbbtc > 1e-8 else ('WETH' if weth > 1e-12 else None)
            holding_units = cbbtc if holding_asset == 'CBBTC' else (weth if holding_asset == 'WETH' else 0.0)
            health = 'green'
            return self.json_response(200, {
                'usdc': usdc,
                'weth': eth,
                'positions': active_positions,
                'health': health,
                'available_capital_usd': usdc,
                'invested_capital_usd': round(invested_capital, 2),
                'compounding_state': 'holding_active_inventory' if active_positions else ('flat_deployable' if usdc > 0 else 'idle_unfunded'),
                'holding_asset': holding_asset,
                'holding_units': holding_units,
                'status_label': 'holding_active_inventory' if active_positions else ('flat_deployable' if usdc > 0 else 'idle_unfunded'),
                'top_blocker': None if active_positions else ('no deployable capital' if usdc <= 0 else None),
            })
        except Exception as e:
            return self.json_response(200, {
                'usdc': 0.0,
                'weth': 0.0,
                'positions': 0,
                'health': 'red'
            })

    def _handle_positions(self):
        """Combine Tradier and Bloc positions"""
        try:
            # Get Tradier positions via position manager
            tradier_data = position_manager.get_live_positions()
            tradier_positions = tradier_data.get('data', {}).get('positions', [])
            bloc_positions = []
            # Get Bloc positions from state file
            positions_path = ROOT / 'eth_scalper' / 'state' / 'positions.json'
            if positions_path.exists():
                with open(positions_path) as f:
                    bloc_data = json.load(f)
                    if isinstance(bloc_data, list):
                        bloc_positions = bloc_data
            # Map Tradier positions to frontend format
            formatted = []
            for pos in tradier_positions:
                side = 'Buy' if pos.get('quantity', 0) > 0 else 'Sell'
                formatted.append({
                    'symbol': pos.get('symbol', ''),
                    'side': side,
                    'entry': pos.get('entry_price', 0.0),
                    'current': pos.get('current_price', 0.0),
                    'pnl': pos.get('pnl_dollar', 0.0)
                })
            # Map Bloc positions (including synthetic inventory-backed holds)
            for pos in bloc_positions:
                formatted.append({
                    'symbol': pos.get('symbol', ''),
                    'side': pos.get('side', 'Buy'),
                    'entry': pos.get('entry_price', 0.0),
                    'current': pos.get('current_price', 0.0),
                    'pnl': pos.get('pnl'),
                    'status': pos.get('status', 'unknown'),
                    'size': pos.get('size') or pos.get('size_usd')
                })
            return self.json_response(200, {'positions': formatted})
        except Exception as e:
            # Fallback to empty on error
            return self.json_response(200, {'positions': []})

    def _load_activity_from_logs(self):
        """Load trade activity from various log files"""
        activity = []
        try:
            # 1. Tradier execution audit log
            audit_path = ROOT / 'out' / 'tradier_execution_audit.jsonl'
            if audit_path.exists():
                with open(audit_path) as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            entry = json.loads(line)
                            if entry.get('action') not in ('execute', 'fill'):
                                continue
                            # Determine timestamp
                            ts = entry.get('ts')
                            if ts:
                                try:
                                    dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                                    time_str = dt.strftime('%H:%M')
                                except Exception:
                                    time_str = '--:--'
                            else:
                                time_str = '--:--'
                            # Determine system
                            system = 'Tradier'
                            # Symbol
                            symbol = entry.get('symbol', '')
                            # Side
                            side = entry.get('side', 'Buy')
                            # P&L not available in audit log
                            pnl = None
                            activity.append({
                                'time': time_str,
                                'system': system,
                                'symbol': symbol,
                                'side': side,
                                'pnl': pnl
                            })
                        except Exception:
                            continue
        except Exception:
            pass
        
        try:
            # 2. ETH scalper trade logs
            scalper_log_path = ROOT / 'eth_scalper' / 'logs' / 'trades.jsonl'
            if scalper_log_path.exists():
                with open(scalper_log_path) as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            entry = json.loads(line)
                            # Look for trade execution messages
                            msg = entry.get('message', '')
                            if 'filled' not in msg.lower() and 'trade' not in msg.lower():
                                continue
                            ts = entry.get('timestamp')
                            if ts:
                                try:
                                    dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                                    time_str = dt.strftime('%H:%M')
                                except Exception:
                                    time_str = '--:--'
                            else:
                                time_str = '--:--'
                            system = 'Bloc'
                            # Try to extract symbol from message
                            symbol = 'ETH'
                            # Side
                            side = 'Buy' if 'buy' in msg.lower() else 'Sell'
                            pnl = None
                            activity.append({
                                'time': time_str,
                                'system': system,
                                'symbol': symbol,
                                'side': side,
                                'pnl': pnl
                            })
                        except Exception:
                            continue
        except Exception:
            pass
        
        # Sort by time descending (most recent first)
        def sort_key(item):
            t = item['time']
            if t == '--:--':
                return datetime.min
            try:
                return datetime.strptime(t, '%H:%M')
            except Exception:
                return datetime.min
        activity.sort(key=sort_key, reverse=True)
        return activity[:10]  # limit to 10

    def _handle_activity(self):
        """Fetch recent trades from trade journal and logs"""
        try:
            # First try trade journal
            journal = trade_journal.load_journal()
            # Sort by entry timestamp descending
            def get_time(entry):
                ts = entry.get('entry', {}).get('timestamp')
                if ts:
                    try:
                        return datetime.fromisoformat(ts.replace('Z', '+00:00'))
                    except Exception:
                        return datetime.min
                return datetime.min
            journal.sort(key=get_time, reverse=True)
            activity = []
            for entry in journal[:10]:  # limit to 10
                entry_data = entry.get('entry', {})
                exit_data = entry.get('exit', {})
                pnl_data = entry.get('pnl', {})
                # Determine time
                ts = entry_data.get('timestamp')
                if ts:
                    try:
                        dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                        time_str = dt.strftime('%H:%M')
                    except Exception:
                        time_str = '--:--'
                else:
                    time_str = '--:--'
                # Determine system
                system = entry.get('signal_source', 'Tradier')
                # Symbol
                symbol = entry_data.get('symbol', '')
                # Side (call/put or buy/sell)
                side = entry_data.get('option_type', 'Buy')
                # P&L if closed
                pnl = pnl_data.get('dollar') if entry.get('status') == 'closed' else None
                activity.append({
                    'time': time_str,
                    'system': system,
                    'symbol': symbol,
                    'side': side,
                    'pnl': pnl
                })
            # If journal empty, fallback to logs
            if not activity:
                activity = self._load_activity_from_logs()
            return self.json_response(200, {'activity': activity})
        except Exception as e:
            # Fallback to logs
            try:
                activity = self._load_activity_from_logs()
                return self.json_response(200, {'activity': activity})
            except Exception:
                # Final fallback empty
                return self.json_response(200, {'activity': []})

    def _handle_command(self, body):
        try:
            payload = json.loads(body.decode() or '{}')
            command = payload.get('command')
            state_path = ROOT / 'eth_scalper' / 'state' / 'bot_state.json'
            state = json.loads(state_path.read_text()) if state_path.exists() else {}

            if command == 'refresh_truth':
                return self._handle_manual_refresh()
            elif command == 'pause_bloc':
                state['status'] = 'paused'
                state['updated_at'] = now_iso()
                state_path.write_text(json.dumps(state, indent=2))
                hq_repository.append_event('operator_command', 'Bloc paused', 'Operator set Bloc status to paused.', 'warning', {'command': command})
                return self.json_response(200, {'ok': True, 'message': 'Bloc paused'})
            elif command == 'resume_bloc':
                state['status'] = 'running'
                state['updated_at'] = now_iso()
                state_path.write_text(json.dumps(state, indent=2))
                hq_repository.append_event('operator_command', 'Bloc resumed', 'Operator set Bloc status to running.', 'info', {'command': command})
                return self.json_response(200, {'ok': True, 'message': 'Bloc resumed'})
            elif command == 'diagnose_tradier':
                tradier_state_path = ROOT / 'out' / 'tradier_account_state.json'
                prior_state = json.loads(tradier_state_path.read_text()) if tradier_state_path.exists() else {}
                refresh_error = None
                try:
                    tradier_proc = subprocess.run(
                        ['python3', str(ROOT / 'scripts' / 'tradier_account.py'), 'ready'],
                        cwd=str(ROOT),
                        capture_output=True,
                        text=True,
                        timeout=45,
                        env=os.environ,
                    )
                    if tradier_proc.returncode == 0:
                        tradier_state = json.loads(tradier_proc.stdout or '{}')
                    else:
                        tradier_state = prior_state
                        refresh_error = (tradier_proc.stderr or tradier_proc.stdout or 'tradier readiness refresh failed').strip()[-400:]
                except Exception as exc:
                    tradier_state = prior_state
                    refresh_error = str(exc)
                buying_power = tradier_state.get('option_buying_power') or tradier_state.get('cash_available') or tradier_state.get('total_cash') or 0.0
                blockers = tradier_state.get('blockers') or []
                checked_at = tradier_state.get('checked_at') or 'unknown'
                message = f'Tradier checked_at={checked_at}, ready={bool(tradier_state.get("ready_for_options_execution"))}, buying_power=${float(buying_power or 0.0):.2f}, blockers={blockers or ["none"]}'
                if refresh_error:
                    message += f' | refresh_error={refresh_error}'
                hq_repository.append_event('operator_command', 'Tradier diagnosis run', message, 'info', {'command': command, 'checked_at': checked_at, 'refresh_error': refresh_error})
                return self.json_response(200, {'ok': refresh_error is None, 'message': message, 'checked_at': checked_at, 'refresh_error': refresh_error, 'state': tradier_state})
            elif command == 'diagnose_bloc':
                wallet_path = ROOT / 'eth_scalper' / 'state' / 'wallet.json'
                trades_log = ROOT / 'eth_scalper' / 'logs' / 'trades.jsonl'
                wallet = json.loads(wallet_path.read_text()) if wallet_path.exists() else {}
                bot_updated_at = state.get('updated_at', 'unknown')
                wallet_updated_at = wallet.get('updated_at', 'unknown')
                wallet_address = wallet.get('address', 'unknown')
                usdc = wallet.get('usdc', 0)
                eth = wallet.get('eth', 0)
                gas = wallet.get('gas', 0)
                last_trade_timestamp = 'unknown'
                last_trade_message = 'none'
                if trades_log.exists():
                    try:
                        last_line = trades_log.read_text(errors='ignore').splitlines()[-1]
                        last_trade = json.loads(last_line) if last_line else {}
                        last_trade_timestamp = last_trade.get('timestamp', 'unknown')
                        last_trade_message = last_trade.get('message', 'none')
                    except Exception:
                        pass
                message = f'Bloc status={state.get("status", "unknown")}, mode={state.get("mode", "unknown")}, daily_trades={state.get("daily_trades", 0)}, bot_updated_at={bot_updated_at}, wallet_updated_at={wallet_updated_at}, last_trade={last_trade_timestamp}, usdc={usdc}, eth={eth}, gas={gas}, wallet={wallet_address}'
                hq_repository.append_event('operator_command', 'Bloc diagnosis run', message, 'info', {'command': command, 'bot_updated_at': bot_updated_at, 'wallet_updated_at': wallet_updated_at, 'last_trade_timestamp': last_trade_timestamp, 'wallet': wallet_address})
                return self.json_response(200, {'ok': True, 'message': message, 'bot_updated_at': bot_updated_at, 'wallet_updated_at': wallet_updated_at, 'last_trade_timestamp': last_trade_timestamp, 'last_trade_message': last_trade_message, 'wallet': wallet, 'bot_state': state})
            elif command == 'pause_tradier':
                hq_repository.append_event('operator_command', 'Tradier pause requested', 'Tradier pause command recorded for operator review.', 'warning', {'command': command})
                return self.json_response(200, {'ok': True, 'message': 'Tradier pause request recorded'})
            elif command == 'close_all':
                hq_repository.append_event('operator_command', 'Emergency close requested', 'Emergency close was requested from HQ.', 'critical', {'command': command})
                return self.json_response(200, {'ok': True, 'message': 'Emergency close request recorded'})
            else:
                return self.json_response(400, {'ok': False, 'error': 'Unknown command'})
        except Exception as e:
            return self.json_response(500, {'ok': False, 'error': str(e)})

    def _handle_hq_notes(self, body):
        try:
            payload = json.loads(body.decode() or '{}')
            note = str(payload.get('note') or '').strip()
            if not note:
                return self.json_response(400, {'ok': False, 'error': 'note required'})
            notes_path = ROOT / 'dashboard' / 'state' / 'hq_operator_notes.jsonl'
            notes_path.parent.mkdir(parents=True, exist_ok=True)
            entry = {'ts': now_iso(), 'note': note}
            with notes_path.open('a', encoding='utf-8') as f:
                f.write(json.dumps(entry) + '\n')
            hq_repository.append_event('operator_note', 'Operator note added', note[:200], 'info', entry)
            return self.json_response(200, {'ok': True, 'message': 'Note saved', 'entry': entry})
        except Exception as e:
            return self.json_response(500, {'ok': False, 'error': str(e)})

    def _handle_hq_config(self, body):
        try:
            payload = json.loads(body.decode() or '{}')
            config = payload.get('config')
            if not isinstance(config, dict):
                return self.json_response(400, {'ok': False, 'error': 'config object required'})
            config_path = ROOT / 'dashboard' / 'config' / 'safety_config.json'
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(json.dumps(config, indent=2))
            hq_repository.append_event('operator_config', 'Safety config updated', 'Operator updated HQ safety configuration.', 'warning', {'keys': list(config.keys())})
            return self.json_response(200, {'ok': True, 'message': 'Config saved'})
        except Exception as e:
            return self.json_response(500, {'ok': False, 'error': str(e)})

    def _handle_hq_overview(self):
        def tail_lines(path, limit=20):
            if not path.exists():
                return []
            return path.read_text(errors='ignore').splitlines()[-limit:]

        def read_json(path, default=None):
            if default is None:
                default = {}
            if not path.exists():
                return default
            try:
                return json.loads(path.read_text())
            except Exception:
                return default

        safety_config = read_json(ROOT / 'dashboard' / 'config' / 'safety_config.json', {})
        risk_config = read_json(ROOT / 'risk_config.json', {})
        refresh_status = read_json(ROOT / 'dashboard' / 'state' / 'refresh_status.json', {})
        action_feedback = read_json(ROOT / 'dashboard' / 'state' / 'action_feedback.json', {})

        notes = tail_lines(ROOT / 'dashboard' / 'state' / 'hq_operator_notes.jsonl', 10)
        signal_lines = tail_lines(ROOT / 'eth_scalper' / 'logs' / 'signals.jsonl', 20)
        trade_lines = tail_lines(ROOT / 'eth_scalper' / 'logs' / 'trades.jsonl', 20)
        refresh_log = tail_lines(ROOT / 'out' / 'logs' / 'bazaar_refresh_cycle.log', 30)
        recent_events = hq_repository.get_recent_events(limit=12)
        latest_result = recent_events[0] if recent_events else None

        return self.json_response(200, {
            'ok': True,
            'notes': notes,
            'signals': signal_lines,
            'trades': trade_lines,
            'refresh_log': refresh_log,
            'safety_config': safety_config,
            'risk_config': risk_config,
            'refresh_status': refresh_status,
            'action_feedback': action_feedback,
            'recent_events': recent_events,
            'latest_result': latest_result,
        })

def parse_args():
    parser = argparse.ArgumentParser(description='Serve the Tradier local dashboard.')
    parser.add_argument('--host', default=os.environ.get('TRADIER_DASHBOARD_HOST', '0.0.0.0'))
    parser.add_argument('--port', type=int, default=int(os.environ.get('TRADIER_DASHBOARD_PORT', '8765')))
    return parser.parse_args()


if __name__ == '__main__':
    args = parse_args()
    os.chdir(PUBLIC)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f'Dashboard serving on http://{args.host}:{args.port}')
    server.serve_forever()
