from __future__ import annotations

from html import escape
from typing import Any

from tradier_ui_render_model import render_tradier_ui_shell
from tradier_web_server import dispatch_request


def build_browser_app_shell(*, latest_limit: int = 20, detail_intent_id: str | None = None) -> dict[str, Any]:
    detail_query = f"&detail_intent_id={detail_intent_id}" if detail_intent_id else ''
    status_code, shell_response = dispatch_request('GET', f'/shell?latest_limit={latest_limit}{detail_query}')
    rendered = render_tradier_ui_shell(shell_response)
    html = render_browser_app_html(rendered)
    return {
        'kind': 'tradier.browser_app_shell',
        'status_code': status_code,
        'render_model': rendered,
        'html': html,
    }


def render_browser_app_html(rendered: dict[str, Any]) -> str:
    overview = rendered['overview_panel']
    worklist_items = ''.join(
        f"<li data-priority='{escape(str(item['priority_rank']))}'><strong>{escape(item['priority_category'])}</strong> — {escape(item['intent_id'])}</li>"
        for item in rendered['worklist_panel']
    )
    detail = rendered['detail_panel']
    actions = rendered['actions_panel'] or {}
    action_items = ''.join(
        f"<li><button data-action='{escape(name)}' {'disabled' if not cfg['available'] else ''}>{escape(name)}</button></li>"
        for name, cfg in actions.items()
    )
    detail_html = ''
    if detail and detail['intent_id']:
        detail_html = (
            f"<section id='detail'>"
            f"<h2>Selected Item</h2>"
            f"<p><strong>Intent:</strong> {escape(detail['intent_id'])}</p>"
            f"<p><strong>Status:</strong> {escape(detail['core']['lifecycle']['status'])}</p>"
            f"<p><strong>Operator State:</strong> {escape(detail['operator']['operator_state'])}</p>"
            f"</section>"
        )

    return f"""
<!doctype html>
<html>
  <head>
    <meta charset='utf-8'>
    <title>Tradier Operator Shell</title>
  </head>
  <body>
    <main id='app-shell'>
      <header>
        <h1>{escape(rendered['header']['title'])}</h1>
        <p>Status: {escape(rendered['header']['status'])}</p>
      </header>
      <section id='overview'>
        <h2>Overview</h2>
        <ul>
          <li>Ready: {overview['ready_count']}</li>
          <li>Blocked: {overview['blocked_count']}</li>
          <li>Pending confirmation: {overview['pending_confirmation_count']}</li>
          <li>Divergent: {overview['divergent_count']}</li>
        </ul>
      </section>
      <section id='worklist'>
        <h2>Worklist</h2>
        <ul>{worklist_items}</ul>
      </section>
      {detail_html}
      <section id='actions'>
        <h2>Actions</h2>
        <ul>{action_items}</ul>
      </section>
    </main>
  </body>
</html>
""".strip()
