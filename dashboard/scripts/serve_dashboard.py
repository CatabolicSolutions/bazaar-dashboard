from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
import subprocess
import os
import json

ROOT = Path('/home/catabolic_solutions/.openclaw/workspace')
PUBLIC = ROOT / 'dashboard' / 'public'
BUILDER = ROOT / 'dashboard' / 'scripts' / 'build_snapshot.py'
SAVE_POSITIONS = ROOT / 'dashboard' / 'scripts' / 'save_positions.py'

class Handler(SimpleHTTPRequestHandler):
    def refresh_snapshot(self):
        try:
            subprocess.run(['bash', '-lc', f'source ~/.profile >/dev/null 2>&1; source ~/.bashrc >/dev/null 2>&1; python3 {BUILDER}'], cwd=str(ROOT), check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

    def do_GET(self):
        self.refresh_snapshot()
        return super().do_GET()

    def do_POST(self):
        if self.path == '/api/positions':
            length = int(self.headers.get('Content-Length', '0'))
            body = self.rfile.read(length)
            proc = subprocess.run(
                ['python3', str(SAVE_POSITIONS)],
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
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'ok': False, 'error': proc.stderr.decode() or 'save failed'}).encode())
            return
        self.send_response(404)
        self.end_headers()

os.chdir(PUBLIC)
server = ThreadingHTTPServer(('127.0.0.1', 8765), Handler)
print('Dashboard serving on http://127.0.0.1:8765')
server.serve_forever()
