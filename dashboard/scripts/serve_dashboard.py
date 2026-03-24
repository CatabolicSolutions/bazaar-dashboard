from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
import subprocess
import os

ROOT = Path('/home/catabolic_solutions/.openclaw/workspace')
PUBLIC = ROOT / 'dashboard' / 'public'
BUILDER = ROOT / 'dashboard' / 'scripts' / 'build_snapshot.py'

class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        try:
            subprocess.run(['bash', '-lc', f'source ~/.profile >/dev/null 2>&1; source ~/.bashrc >/dev/null 2>&1; python3 {BUILDER}'], cwd=str(ROOT), check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass
        return super().do_GET()

os.chdir(PUBLIC)
server = ThreadingHTTPServer(('127.0.0.1', 8765), Handler)
print('Dashboard serving on http://127.0.0.1:8765')
server.serve_forever()
