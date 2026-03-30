import json
import subprocess
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path


WORKSPACE_ROOT = Path('/home/catabolic_solutions/.openclaw/workspace')
SERVER_SCRIPT = WORKSPACE_ROOT / 'dashboard' / 'scripts' / 'serve_dashboard.py'
QUEUE_PATH = WORKSPACE_ROOT / 'dashboard' / 'state' / 'execution_queue.json'
POSITIONS_PATH = WORKSPACE_ROOT / 'dashboard' / 'state' / 'active_positions.json'
FEEDBACK_PATH = WORKSPACE_ROOT / 'dashboard' / 'state' / 'action_feedback.json'
APP_JS = WORKSPACE_ROOT / 'dashboard' / 'public' / 'app.js'
INDEX_HTML = WORKSPACE_ROOT / 'dashboard' / 'public' / 'index.html'
STYLES = WORKSPACE_ROOT / 'dashboard' / 'public' / 'styles.css'
BASE_URL = 'http://127.0.0.1:8765'


class TradierDashboardSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._backup_dir = Path(tempfile.mkdtemp(prefix='tradier-dashboard-smoke-'))
        cls._queue_backup = cls._backup_dir / 'execution_queue.json'
        cls._positions_backup = cls._backup_dir / 'active_positions.json'
        cls._feedback_backup = cls._backup_dir / 'action_feedback.json'
        cls._queue_backup.write_text(QUEUE_PATH.read_text(encoding='utf-8'), encoding='utf-8')
        cls._positions_backup.write_text(POSITIONS_PATH.read_text(encoding='utf-8'), encoding='utf-8')
        if FEEDBACK_PATH.exists():
            cls._feedback_backup.write_text(FEEDBACK_PATH.read_text(encoding='utf-8'), encoding='utf-8')

        subprocess.run('fuser -k 8765/tcp 2>/dev/null || true', shell=True, cwd=str(WORKSPACE_ROOT), check=False)
        cls._server = subprocess.Popen(
            ['python3', str(SERVER_SCRIPT)],
            cwd=str(WORKSPACE_ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(1.0)

    @classmethod
    def tearDownClass(cls):
        try:
            if cls._server.poll() is None:
                cls._server.terminate()
                cls._server.wait(timeout=5)
        except Exception:
            pass

        QUEUE_PATH.write_text(cls._queue_backup.read_text(encoding='utf-8'), encoding='utf-8')
        POSITIONS_PATH.write_text(cls._positions_backup.read_text(encoding='utf-8'), encoding='utf-8')
        if cls._feedback_backup.exists():
            FEEDBACK_PATH.write_text(cls._feedback_backup.read_text(encoding='utf-8'), encoding='utf-8')
        elif FEEDBACK_PATH.exists():
            FEEDBACK_PATH.unlink()

        try:
            urllib.request.urlopen(BASE_URL + '/snapshot.json').read()
        except Exception:
            pass

    def get_json(self, path: str):
        return json.loads(urllib.request.urlopen(BASE_URL + path).read().decode())

    def post_action(self, payload: dict):
        req = urllib.request.Request(
            BASE_URL + '/api/actions',
            data=json.dumps(payload).encode(),
            headers={'Content-Type': 'application/json'},
            method='POST',
        )
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())

    def test_dashboard_selected_item_coherence_smoke(self):
        snapshot = self.get_json('/snapshot.json')
        leaders = snapshot['tradier']['leaders']
        self.assertGreater(len(leaders), 0)

        leader = leaders[0]
        leader_identity = '|'.join([
            leader['symbol'],
            leader['exp'],
            leader['strike'],
            leader['option_type'],
            leader['section'],
        ])
        instrument = f"{leader['exp']} {leader['strike']} {leader['option_type']}"

        queue_result = self.post_action({'action': 'queue_selected_leader', 'leader': leader})
        watch_result = self.post_action({'action': 'watch_selected_leader', 'leader': leader})
        refreshed = self.get_json('/snapshot.json')

        matching_leaders = [
            item for item in refreshed['tradier']['leaders']
            if '|'.join([item['symbol'], item['exp'], item['strike'], item['option_type'], item['section']]) == leader_identity
        ]
        self.assertEqual(len(matching_leaders), 1)

        queue_item = next(
            item for item in refreshed['executionQueue']['queue']
            if item['symbol'] == leader['symbol'] and item['instrument'] == instrument
        )
        watch_item = next(
            item for item in refreshed['activePositions']['positions']
            if item['symbol'] == leader['symbol'] and item['instrument'] == instrument and item['status'] == 'watch'
        )
        feedback = refreshed['tradier']['actionFeedback']['feedback']

        self.assertEqual(queue_item['trigger'], leader['entry'])
        self.assertEqual(watch_item['invalidation'], leader['invalidation'])
        self.assertEqual(feedback['symbol'], leader['symbol'])
        self.assertEqual(feedback['instrument'], instrument)
        self.assertEqual(feedback['action'], 'watch_selected_leader')
        self.assertIn('tracked in local watch state', feedback['stateChange'])
        self.assertEqual(queue_result['action'], 'queue_selected_leader')
        self.assertEqual(watch_result['action'], 'watch_selected_leader')

        app_js = APP_JS.read_text(encoding='utf-8')
        index_html = INDEX_HTML.read_text(encoding='utf-8')
        styles = STYLES.read_text(encoding='utf-8')

        for needle in [
            'renderSummaryStrip',
            'Latest Local Action',
            'Latest State Change',
            'coherent after refresh',
            'Selected Key',
            'Recent Action Result',
            'Visible state: queued',
            'Visible state: watching',
        ]:
            self.assertIn(needle, app_js)

        for needle in ['Operator Summary', 'Ticket Detail', 'Actions']:
            self.assertIn(needle, index_html)

        for needle in ['.card-summary-strip', '.summary-strip-grid', '.status-chip.recent']:
            self.assertIn(needle, styles)


if __name__ == '__main__':
    unittest.main()
