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
        if self.path in ('/', '/hq', '/war-room', '/war-room/'):
            return self._handle_war_room_page()
        elif self.path in ('/legacy', '/legacy/'):
            self.path = '/index.html'
        elif self.path == '/api/live-positions':
            return self._handle_live_positions()
        elif self.path == '/api/live-scanner':
            return self._handle_live_scanner()
        elif self.path == '/api/exit-predictor':
            return self._handle_exit_predictor()
        elif self.path == '/api/journal':
            return self._handle_journal()
        elif self.path == '/api/analytics':
            return self._handle_analytics()
        elif self.path == '/api/premarket':
            return self._handle_premarket()
        elif self.path == '/api/heatmap':
            return self._handle_heatmap()
        elif self.path == '/api/crypto/init':
            return self._handle_crypto_init()
        elif self.path == '/api/crypto/wallet':
            return self._handle_crypto_wallet()
        elif self.path == '/api/crypto/pairs':
            return self._handle_crypto_pairs()
        elif self.path == '/api/crypto/emergency':
            return self._handle_crypto_emergency()
        elif self.path.startswith('/api/underlying-history'):
            return self._handle_underlying_history()
        elif self.path == '/api/refresh-status':
            return self._handle_refresh_status()
        elif self.path.startswith('/api/narrative'):
            return self._handle_narrative()
        elif self.path == '/api/account':
            return self._handle_account()
        elif self.path == '/api/tradier/status':
            return self._handle_tradier_status()
        elif self.path == '/api/bloc/status':
            return self._handle_bloc_status()
        elif self.path == '/api/sie/status':
            return self._handle_sie_status()
        elif self.path == '/api/positions':
            return self._handle_positions()
        elif self.path == '/api/activity':
            return self._handle_activity()
        elif self.path == '/api/eth-scalper/status':
            return self._handle_eth_scalper_status()
        elif self.path == '/api/hq/status':
            return self._handle_hq_status()
        elif self.path == '/api/eth-scalper/trades':
            return self._handle_eth_scalper_trades()
        elif self.path == '/api/eth-scalper/positions':
            return self._handle_eth_scalper_positions()
        elif self.path == '/api/eth-scalper/signals':
            return self._handle_eth_scalper_signals()
        elif self.path == '/api/eth-scalper/wallet':
            return self._handle_eth_scalper_wallet()
        elif self.path.startswith('/eth-scalper/logs'):
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

            if proc.returncode == 0:
                self.refresh_snapshot()
                status = self._canonical_refresh_payload(
                    ok=True,
                    stage='complete',
                    message='Manual refresh completed',
                    stdout_tail=proc.stdout or '',
                    stderr_tail=proc.stderr or '',
                )
                self.write_json(REFRESH_STATUS_STATE, status)
                return self.json_response(200, {'ok': True, 'data': status})

            status = self._canonical_refresh_payload(
                ok=False,
                stage='failed',
                message=((proc.stderr or proc.stdout or 'Manual refresh failed').strip()[-400:]) or 'Manual refresh failed',
                stdout_tail=proc.stdout or '',
                stderr_tail=proc.stderr or '',
            )
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
        tradier_balances = tradier_state.get('balances', {}) if isinstance(tradier_state, dict) else {}
        tradier_buying_power = tradier_balances.get('total_cash') or tradier_balances.get('cash_available') or tradier_state.get('buying_power') or 0.0
        tradier_positions = tradier_state.get('positions') or []
        tradier_orders = tradier_state.get('orders') or []
        tradier_ready = float(tradier_buying_power or 0.0) > 0
        tradier_blocker = None if tradier_ready else 'No Tradier buying power detected.'

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
        primary_directive = (
            'Manage active Bloc inventory and avoid forcing fresh exposure.'
            if compounding_state == 'holding_active_inventory'
            else ('Tradier is funded. Hunt only clean, high-clarity setups.' if tradier_ready else 'Stay flat. Restore readiness and wait for valid edge.')
        )
        next_actions = []
        if compounding_state == 'holding_active_inventory':
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
            'build': 'HQv10-ruthless-operator-product-2026-04-20',
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
                    f'Holding {holding_asset} inventory, manage recycle and exit quality.'
                    if compounding_state == 'holding_active_inventory' and holding_asset
                    else ('Deployable cash available for next entry.' if deployable_capital > 0 else 'No funded deployable state detected.')
                ),
                'operator_focus': (
                    'Supervise live inventory, protect gains, and recycle only on valid edge.'
                    if compounding_state == 'holding_active_inventory'
                    else ('Wait for valid edge and funded conditions.' if deployable_capital > 0 else 'Restore funding or runtime prerequisites.')
                ),
                'primary_directive': primary_directive,
                'next_actions': next_actions,
                'wallet': wallet,
                'active_positions': len(cleaned_positions) or (1 if compounding_state == 'holding_active_inventory' else 0),
                'positions': cleaned_positions,
                'reconciled_positions': cleaned_positions,
                'tradier': {
                    'ready': tradier_ready,
                    'status': 'ready' if tradier_ready else 'idle',
                    'buying_power_usd': round(float(tradier_buying_power or 0.0), 2),
                    'positions_count': len(tradier_positions) if isinstance(tradier_positions, list) else 0,
                    'orders_count': len(tradier_orders) if isinstance(tradier_orders, list) else 0,
                    'top_blocker': tradier_blocker,
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
            latest['events'] = hq_repository.get_recent_events(limit=12)
            payload = latest
        except Exception:
            pass

        live = payload.get('live') or {}
        wallet = live.get('wallet') or {}
        positions = live.get('positions') or []
        events = payload.get('events') or []
        tradier = live.get('tradier') or {}
        next_actions_data = live.get('next_actions') or []
        holding_asset = live.get('holding_asset') or 'Inventory'
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

        html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>HQ — Bazaar Operator Console</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
    <style>{war_room_style}</style>
</head>
<body>
    <div class="shell">
        <section class="card hero">
            <div class="hero-top">
                <div>
                    <div class="eyebrow">Bazaar of Fortunes</div>
                    <h1>HQ Operator Console</h1>
                    <div class="subline">Live operator truth for deployed capital, blockers, execution posture, and next action. Legacy dashboard moved to /legacy.</div>
                </div>
                <div class="asof">Updated {esc(updated_at)} | {esc(payload.get('build'))} | db {esc(persistence)}</div>
            </div>
            <div class="status-strip">
                <div class="pill-card"><div class="pill-label">Primary Decision</div><div class="pill-value">{esc('Manage active compounding inventory' if status == 'holding_active_inventory' else 'Monitor live state')}</div><div class="pill-sub">{esc(operator_summary)}</div></div>
                <div class="pill-card"><div class="pill-label">Tradier Readiness</div><div class="pill-value mono">{esc(tradier_status)}</div><div class="pill-sub">{esc((money(tradier_buying_power) + ' buying power') if tradier_status == 'Ready' else (tradier.get('top_blocker') or 'Separate execution path'))}</div></div>
                <div class="pill-card"><div class="pill-label">Bloc Readiness</div><div class="pill-value mono">{esc('Holding active inventory' if status == 'holding_active_inventory' else 'Bloc runtime')}</div><div class="pill-sub">{esc(holding_asset + ' | ' + money(invested) + ' invested' if status == 'holding_active_inventory' else money(deployable) + ' deployable')}</div></div>
                <div class="pill-card"><div class="pill-label">Live Exposure</div><div class="pill-value mono">{esc(str(active_positions) + (' position' if active_positions == 1 else ' positions'))}</div><div class="pill-sub">{esc('Active compounding inventory requires supervision' if status == 'holding_active_inventory' else 'No active risk detected')}</div></div>
                <div class="pill-card"><div class="pill-label">SQL Persistence</div><div class="pill-value mono">{esc(sql_status)}</div><div class="pill-sub">{esc(sql_detail)}</div></div>
            </div>
            <div class="decision">
                <div class="decision-head"><div><div class="eyebrow">Operator directive</div><div class="decision-title">{esc('Manage compounding hold' if status == 'holding_active_inventory' else 'Stand by')}</div></div><div class="decision-badge badge-amber">{esc('ACTIVE HOLD' if status == 'holding_active_inventory' else 'MONITORING')}</div></div>
                <div class="decision-copy">{esc(primary_directive)}</div>
                <div class="pill-sub">{esc('Yesterday\'s lesson: the old dashboard kept drifting into disconnected UI, stale routes, and runtime mismatch. HQ now stays decision-first, with SQL called out explicitly and legacy UI isolated behind /legacy.')}</div>
                <div class="decision-grid">
                    <div class="mini-stat"><div class="label">Tradier capital</div><div class="value mono">--</div></div>
                    <div class="mini-stat"><div class="label">Bloc capital</div><div class="value mono">{esc((money(invested) + ' in ' + holding_asset) if status == 'holding_active_inventory' else money(deployable))}</div></div>
                    <div class="mini-stat"><div class="label">Reality feed</div><div class="value mono">{esc(reality_feed)}</div></div>
                </div>
            </div>
        </section>
        <div class="grid">
            <div class="stack">
                <section class="card section"><div class="section-head"><div><div class="section-title">System readiness</div><div class="section-sub">Condensed truth for each execution path</div></div></div><div class="ops-list"><div class="ops-item"><div class="ops-item-head"><div class="ops-name">Tradier</div><div class="decision-badge badge-amber">{esc(tradier_status.upper())}</div></div><div class="ops-summary">{esc('Options execution path is separate from Bloc inventory. It should surface capital, readiness, and blockers, not decorative widgets.')}</div><div class="kv"><div><span>Status</span>{esc(tradier_status)}</div><div><span>Buying power</span>{money(tradier_buying_power)}</div><div><span>Route</span>/api/tradier/status</div><div><span>Role</span>Options / ticket execution</div></div><div class="blocker"><strong>Top lesson:</strong> stale UI without live execution truth is noise.</div></div><div class="ops-item"><div class="ops-item-head"><div class="ops-name">Bloc</div><div class="decision-badge badge-amber">{esc(str(live.get('mode') or 'live').upper())}</div></div><div class="ops-summary">{esc(('Holding ' + holding_asset + ' for managed recycle.') if status == 'holding_active_inventory' else 'Runtime connected.')}</div><div class="kv"><div><span>State</span>{esc(status)}</div><div><span>Persistence</span>{esc(persistence)}</div><div><span>Holding</span>{esc(holding_asset + (' ' + str(holding_units) if holding_units is not None else ''))}</div><div><span>Invested</span>{money(invested)}</div><div><span>Deployable</span>{money(deployable)}</div><div><span>Wallet USDC</span>{money(wallet.get('usdc') or 0.0)}</div></div><div class="blocker"><strong>Operator focus:</strong> {esc(operator_focus)}</div></div><div class="ops-item"><div class="ops-item-head"><div class="ops-name">HQ / SQL</div><div class="decision-badge badge-amber">{esc(sql_status.upper())}</div></div><div class="ops-summary">{esc('HQ should be the canonical landing layer for system truth, event trail, and operator decisions.')}</div><div class="kv"><div><span>Persistence</span>{esc(persistence)}</div><div><span>Database</span>{esc('PostgreSQL' if persistence == 'postgresql' else 'Not connected')}</div><div><span>Snapshot path</span>/api/hq/status</div><div><span>Legacy UI</span>/legacy</div></div><div class="blocker"><strong>Current truth:</strong> {esc(sql_detail)}</div></div></div></section>
                <section class="card section"><div class="section-head"><div><div class="section-title">Active positions</div><div class="section-sub">Only live risk that needs attention</div></div></div><div class="positions-list">{positions_html}</div></section>
            </div>
            <div class="stack">
                <section class="card section"><div class="section-head"><div><div class="section-title">Next best actions</div><div class="section-sub">What to do next, in order</div></div></div><div class="next-action-list"><div class="next-action"><div class="num">0</div><div class="action-copy"><strong>Landing principle</strong>HQ is the decision-first landing page. War Room remains the live operator shell. Legacy dashboard is still available, but no longer owns first impression.</div></div>{next_actions_html}</div></section>
                <section class="card section"><div class="section-head"><div><div class="section-title">Recent activity</div><div class="section-sub">Latest execution and journal trail</div></div></div><div class="activity-list">{events_html}</div></section>
                <section class="card section"><div class="section-head"><div><div class="section-title">Operator notes</div><div class="section-sub">Surface intent, not clutter</div></div></div><div class="ops-item"><div class="ops-summary">Root now serves HQ-first operator truth. Old dashboard remains available at <span class="mono">/legacy</span>.</div><div class="kv"><div><span>Build</span>{esc(payload.get('build'))}</div><div><span>Persistence</span>{esc(persistence)}</div><div><span>Route</span>/</div><div><span>Legacy</span>/legacy</div></div></div><div class="ops-item" style="margin-top:10px;"><div class="ops-summary">Use this page for real decisions: capital, blockers, active inventory, and next action. If a view does not change behavior, it should probably die.</div></div></section>
            </div>
        </div>
    </div>
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
            if command == 'pause_bloc':
                # TODO: implement pause
                return self.json_response(200, {'ok': True, 'message': 'Bloc paused'})
            elif command == 'pause_tradier':
                # TODO: implement pause
                return self.json_response(200, {'ok': True, 'message': 'Tradier paused'})
            elif command == 'close_all':
                # TODO: implement emergency close
                return self.json_response(200, {'ok': True, 'message': 'Emergency close initiated'})
            else:
                return self.json_response(400, {'ok': False, 'error': 'Unknown command'})
        except Exception as e:
            return self.json_response(500, {'ok': False, 'error': str(e)})

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
