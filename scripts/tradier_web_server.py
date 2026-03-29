from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from tradier_browser_app_shell import build_browser_app_shell
from tradier_web_shell_action_endpoint import post_tradier_web_shell_action
from tradier_web_shell_endpoint import get_tradier_web_shell_response


def dispatch_request(method: str, path: str, body: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
    parsed = urlparse(path)
    query = parse_qs(parsed.query)

    if method == 'GET' and parsed.path == '/shell':
        latest_limit = int(query.get('latest_limit', ['20'])[0])
        detail_intent_id = query.get('detail_intent_id', [None])[0]
        return 200, get_tradier_web_shell_response(latest_limit=latest_limit, detail_intent_id=detail_intent_id)

    if method == 'GET' and parsed.path == '/app':
        latest_limit = int(query.get('latest_limit', ['20'])[0])
        detail_intent_id = query.get('detail_intent_id', [None])[0]
        page = build_browser_app_shell(latest_limit=latest_limit, detail_intent_id=detail_intent_id)
        return 200, {'kind': 'tradier.browser_page_response', 'status': 'ok', 'data': page}

    if method == 'POST' and parsed.path == '/shell/action':
        payload = body or {}
        latest_limit = int(payload.get('latest_limit', 20))
        response = post_tradier_web_shell_action(
            payload['intent_id'],
            payload['action_name'],
            payload.get('params') or {},
            latest_limit=latest_limit,
        )
        status_code = 200 if response['status'] == 'ok' else 400 if response['status'] == 'rejected' else 404
        return status_code, response

    return 404, {'status': 'not_found', 'error': f'Unknown route: {method} {parsed.path}'}


class TradierWebHandler(BaseHTTPRequestHandler):
    def _send_json(self, status_code: int, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload).encode('utf-8')
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:
        status_code, payload = dispatch_request('GET', self.path)
        self._send_json(status_code, payload)

    def do_POST(self) -> None:
        length = int(self.headers.get('Content-Length', '0'))
        raw = self.rfile.read(length) if length > 0 else b'{}'
        body = json.loads(raw.decode('utf-8') or '{}')
        status_code, payload = dispatch_request('POST', self.path, body)
        self._send_json(status_code, payload)


def run_server(host: str = '127.0.0.1', port: int = 8000) -> HTTPServer:
    server = HTTPServer((host, port), TradierWebHandler)
    return server


if __name__ == '__main__':
    server = run_server()
    print('Tradier web server listening on http://127.0.0.1:8000')
    server.serve_forever()
