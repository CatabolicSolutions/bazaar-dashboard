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
        f"<li class='worklist-item' data-priority='{escape(str(item['priority_rank']))}'><strong>{escape(item['priority_category'])}</strong> — {escape(item['intent_id'])}</li>"
        for item in rendered['worklist_panel']
    )
    detail = rendered['detail_panel']
    actions = rendered['actions_panel'] or {}
    action_items = ''.join(
        f"<li class='action-item'><button class='touch-target' data-action='{escape(name)}' {'disabled' if not cfg['available'] else ''}>{escape(name)}</button></li>"
        for name, cfg in actions.items()
    )
    detail_html = ''
    next_actions_html = ''
    if detail and detail['intent_id']:
        available_actions = [name for name, cfg in actions.items() if cfg['available']]
        unavailable_actions = [name for name, cfg in actions.items() if not cfg['available']]
        next_actions_html = (
            f"<section id='next-actions' class='panel next-actions-panel'>"
            f"<h2>Next Actions</h2>"
            f"<p class='operator-guidance'><strong>Primary next step:</strong> {escape(available_actions[0] if available_actions else 'No action available')}</p>"
            f"<p><strong>Available now:</strong> {escape(', '.join(available_actions) if available_actions else 'None')}</p>"
            f"<p><strong>Blocked now:</strong> {escape(', '.join(unavailable_actions) if unavailable_actions else 'None')}</p>"
            f"</section>"
        )
        detail_html = (
            f"<section id='detail' class='panel detail-panel'>"
            f"<h2>Selected Item</h2>"
            f"<p><strong>Intent:</strong> {escape(detail['intent_id'])}</p>"
            f"<p><strong>Status:</strong> {escape(detail['core']['lifecycle']['status'])}</p>"
            f"<p><strong>Operator State:</strong> {escape(detail['operator']['operator_state'])}</p>"
            f"<p><strong>Decision:</strong> {escape(detail['core']['decision']['decision_state'])}</p>"
            f"<p><strong>Readiness:</strong> {escape(detail['core']['readiness']['readiness_state'])}</p>"
            f"<p><strong>Reconciliation:</strong> {escape(detail['recent_context']['reconciliation_state'])}</p>"
            f"</section>"
        )

    return f"""
<!doctype html>
<html>
  <head>
    <meta charset='utf-8'>
    <meta name='viewport' content='width=device-width, initial-scale=1'>
    <title>Tradier Operator Shell</title>
    <style>
      :root {{ color-scheme: light dark; }}
      body {{ margin: 0; font-family: system-ui, sans-serif; line-height: 1.4; }}
      #app-shell {{ display: grid; grid-template-columns: 1fr; gap: 12px; padding: 12px; max-width: 1200px; margin: 0 auto; }}
      .panel {{ border: 1px solid #8884; border-radius: 12px; padding: 12px; background: #ffffff08; }}
      .touch-target {{ min-height: 44px; padding: 10px 12px; width: 100%; text-align: left; }}
      .worklist-item, .action-item {{ margin: 8px 0; }}
      @media (min-width: 900px) {{
        #app-shell.responsive-shell {{ grid-template-columns: 1fr 1fr; align-items: start; }}
        #overview, #worklist {{ grid-column: 1; }}
        #detail, #actions {{ grid-column: 2; }}
      }}
    </style>
  </head>
  <body>
    <main id='app-shell' class='responsive-shell mobile-first'>
      <header class='panel'>
        <h1>{escape(rendered['header']['title'])}</h1>
        <p>Status: {escape(rendered['header']['status'])}</p>
      </header>
      <section id='overview' class='panel overview-panel'>
        <h2>Overview</h2>
        <ul>
          <li>Ready: {overview['ready_count']}</li>
          <li>Blocked: {overview['blocked_count']}</li>
          <li>Pending confirmation: {overview['pending_confirmation_count']}</li>
          <li>Divergent: {overview['divergent_count']}</li>
        </ul>
      </section>
      <section id='worklist' class='panel worklist-panel'>
        <h2>Worklist</h2>
        <ul>{worklist_items}</ul>
      </section>
      {detail_html}
      {next_actions_html}
      <section id='actions' class='panel actions-panel'>
        <h2>Actions</h2>
        <p class='operator-guidance'>Use available actions below for the selected item. Disabled actions are intentionally not currently allowed.</p>
        <ul>{action_items}</ul>
      </section>
    </main>
  </body>
</html>
""".strip()
