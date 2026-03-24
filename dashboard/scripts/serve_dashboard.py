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
            subprocess.run(['python3', str(BUILDER)], cwd=str(ROOT), check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass
        return super().do_GET()

os.chdir(PUBLIC)
server = ThreadingHTTPServer(('0.0.0.0', 8765), Handler)
print('Dashboard serving on http://0.0.0.0:8765')
server.serve_forever()
