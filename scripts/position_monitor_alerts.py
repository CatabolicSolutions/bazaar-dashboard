import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORT_FILE = ROOT / 'out' / 'position_monitor_report.json'
ALERTS_FILE = ROOT / 'out' / 'position_monitor_alerts.json'


def build_alerts(report):
    alerts = []
    for row in report:
        if row['alert_level'] == 'high':
            alerts.append({
                'severity': 'high',
                'symbol': row['symbol'],
                'option_symbol': row['option_symbol'],
                'message': f"{row['symbol']} alert: {row['alert_reason']} | mid={row['current_mid']:.2f} | underlying={row['underlying_last']:.2f} | pnl={row['pnl_pct']:.2f}%",
                'action': 'review immediately',
            })
        elif row['alert_level'] == 'medium':
            alerts.append({
                'severity': 'medium',
                'symbol': row['symbol'],
                'option_symbol': row['option_symbol'],
                'message': f"{row['symbol']} threshold hit: {row['alert_reason']} | mid={row['current_mid']:.2f} | underlying={row['underlying_last']:.2f} | pnl={row['pnl_pct']:.2f}%",
                'action': 'check for trim/exit setup',
            })
    return alerts


def main():
    report = json.loads(REPORT_FILE.read_text())
    alerts = build_alerts(report)
    ALERTS_FILE.write_text(json.dumps(alerts, indent=2), encoding='utf-8')
    print(json.dumps(alerts, indent=2))


if __name__ == '__main__':
    main()
