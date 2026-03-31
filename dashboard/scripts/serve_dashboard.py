from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
import subprocess
import os
import json
import argparse
from datetime import datetime, timezone

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

ROOT = Path('/home/catabolic_solutions/.openclaw/workspace')
PUBLIC = ROOT / 'dashboard' / 'public'
BUILDER = ROOT / 'dashboard' / 'scripts' / 'build_snapshot.py'
SAVE_POSITIONS = ROOT / 'dashboard' / 'scripts' / 'save_positions.py'
SAVE_QUEUE = ROOT / 'dashboard' / 'scripts' / 'save_queue.py'
EXECUTE_LEADER = ROOT / 'dashboard' / 'scripts' / 'execute_leader.py'
POSITIONS_STATE = ROOT / 'dashboard' / 'state' / 'active_positions.json'
QUEUE_STATE = ROOT / 'dashboard' / 'state' / 'execution_queue.json'
ACTION_FEEDBACK_STATE = ROOT / 'dashboard' / 'state' / 'action_feedback.json'


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
        path.write_text(json.dumps(payload, indent=2))

    def json_response(self, status_code, payload):
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode())

    def do_GET(self):
        self.refresh_snapshot()
        if self.path in ('/app', '/app/'):
            self.path = '/index.html'
        return super().do_GET()

    def _run_save(self, script_path, body):
        proc = subprocess.run(
            ['python3', str(script_path)],
            input=body,
            cwd=str(ROOT),
            capture_output=True,
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
            text=True
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
            text=True
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
        if self.path in ('/app', '/app/'):
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
        return super().do_GET()
    
    def _handle_live_positions(self):
        """Get live position data from Tradier"""
        import subprocess
        import json as json_mod
        
        proc = subprocess.run(
            ['python3', str(ROOT / 'dashboard' / 'scripts' / 'position_manager.py'), '--get-positions'],
            cwd=str(ROOT),
            capture_output=True,
            text=True
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
            text=True
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
            text=True
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
            text=True
        )
        
        try:
            result = json_mod.loads(proc.stdout)
            if result.get('ok'):
                return self.json_response(200, result)
            else:
                return self.json_response(500, result)
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
        if self.path == '/api/close-position':
            return self._handle_close_position(body)
        if self.path == '/api/journal/export':
            return self._handle_journal_export()
        self.send_response(404)
        self.end_headers()
    
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
            text=True
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
