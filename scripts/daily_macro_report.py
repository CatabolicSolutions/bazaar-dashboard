import argparse
import json
import math
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote

import requests

TIMEZONE = 'America/Denver'
OUT_PATH = Path.home() / '.openclaw' / 'workspace' / 'out' / 'daily_macro_report.md'
JSON_PATH = Path.home() / '.openclaw' / 'workspace' / 'out' / 'daily_macro_report.json'
USER_AGENT = {'User-Agent': 'Mozilla/5.0 Alfred/1.0'}


def get_json(url):
    r = requests.get(url, headers=USER_AGENT, timeout=25)
    r.raise_for_status()
    return r.json()


def get_text(url):
    r = requests.get(url, headers=USER_AGENT, timeout=25)
    r.raise_for_status()
    return r.text


def yahoo_chart(symbol, range_='10d', interval='1d', prepost=True):
    url = f'https://query1.finance.yahoo.com/v8/finance/chart/{quote(symbol)}?range={range_}&interval={interval}&includePrePost={str(prepost).lower()}'
    data = get_json(url)
    result = data['chart']['result'][0]
    return result


def chart_prev_day_levels(symbol):
    result = yahoo_chart(symbol, range_='10d', interval='1d', prepost=True)
    q = result['indicators']['quote'][0]
    highs = q['high']
    lows = q['low']
    closes = q['close']
    timestamps = result['timestamp']
    rows = []
    for ts, h, l, c in zip(timestamps, highs, lows, closes):
        if h is None or l is None or c is None:
            continue
        rows.append({'ts': ts, 'high': float(h), 'low': float(l), 'close': float(c)})
    if len(rows) < 2:
        raise RuntimeError(f'Not enough OHLC rows for {symbol}')
    prev = rows[-2]
    pivot = (prev['high'] + prev['low'] + prev['close']) / 3.0
    r1 = 2 * pivot - prev['low']
    s1 = 2 * pivot - prev['high']
    return {
        'symbol': symbol,
        'high': prev['high'],
        'low': prev['low'],
        'close': prev['close'],
        'pivot': pivot,
        'r1': r1,
        's1': s1,
    }


def get_vix_context():
    result = yahoo_chart('^VIX', range_='3mo', interval='1d', prepost=True)
    meta = result['meta']
    q = result['indicators']['quote'][0]
    closes = [float(x) for x in q['close'] if x is not None]
    current = float(meta.get('regularMarketPrice') or closes[-1])
    yesterday = closes[-2]
    recent = closes[-6:-1] if len(closes) >= 6 else closes[:-1]
    week_avg = sum(recent) / len(recent) if recent else yesterday
    delta_day = current - yesterday
    pct_day = (delta_day / yesterday) * 100 if yesterday else 0.0
    recent_floor = min(recent) if recent else yesterday
    recent_ceiling = max(recent) if recent else yesterday
    if pct_day >= 3:
        trend = 'trending up / fear expanding'
    elif pct_day <= -3:
        trend = 'trending down / fear compressing'
    else:
        trend = 'roughly stable / mixed risk tone'
    return {
        'current': current,
        'yesterday': yesterday,
        'week_avg': week_avg,
        'recent_floor': recent_floor,
        'recent_ceiling': recent_ceiling,
        'pct_day': pct_day,
        'trend': trend,
    }


def get_google_news(query, limit=5):
    url = f'https://news.google.com/rss/search?q={quote(query)}&hl=en-US&gl=US&ceid=US:en'
    xml_text = get_text(url)
    root = ET.fromstring(xml_text)
    items = []
    for item in root.findall('./channel/item')[:limit]:
        title = (item.findtext('title') or '').strip()
        link = (item.findtext('link') or '').strip()
        pub = (item.findtext('pubDate') or '').strip()
        dt = None
        if pub:
            try:
                dt = parsedate_to_datetime(pub)
            except Exception:
                dt = None
        items.append({'title': title, 'link': link, 'published': pub, 'dt': dt})
    return items


def get_overnight_drivers(limit=3):
    queries = [
        'overnight markets Reuters OR CNBC OR Bloomberg',
        'Asia Europe markets overnight stocks Reuters OR CNBC',
        'US stock futures overnight geopolitical earnings Reuters OR CNBC',
    ]
    seen = set()
    picked = []
    for query in queries:
        for item in get_google_news(query, limit=6):
            title = item['title']
            low = title.lower()
            if title in seen:
                continue
            if any(bad in low for bad in ['sport', 'entertainment', 'celebrity', 'movie']):
                continue
            seen.add(title)
            picked.append(item)
            if len(picked) >= limit:
                return picked
    return picked[:limit]


def normalize_time_string(s):
    s = s.strip().lower()
    s = s.replace(' ', '')
    return s


def parse_ff_date(date_s, time_s, year_hint=None):
    if not date_s or not time_s:
        return None
    ds = date_s.strip()
    ts = time_s.strip().lower()
    if ts in {'all day', 'tentative'}:
        return None
    try:
        dt = datetime.strptime(f'{ds} {ts}', '%m-%d-%Y %I:%M%p')
        return dt
    except Exception:
        return None


def get_us_econ_events(limit=4):
    xml_text = get_text('https://nfs.faireconomy.media/ff_calendar_thisweek.xml')
    root = ET.fromstring(xml_text)
    now = datetime.now()
    today = now.date()
    tomorrow = today + timedelta(days=1)
    important_terms = ['cpi', 'inflation', 'gdp', 'jobless', 'payroll', 'employment', 'fomc', 'fed', 'powell', 'pce', 'retail sales', 'ism', 'consumer confidence', 'treasury', 'auction']
    scored = []
    for ev in root.findall('./event'):
        country = (ev.findtext('country') or '').strip().upper()
        if country != 'USD':
            continue
        title = (ev.findtext('title') or '').strip()
        date_s = (ev.findtext('date') or '').strip()
        time_s = (ev.findtext('time') or '').strip()
        impact = (ev.findtext('impact') or '').strip().title()
        dt = parse_ff_date(date_s, time_s)
        if not dt or dt.date() not in {today, tomorrow}:
            continue
        title_low = title.lower()
        keyword_hit = any(term in title_low for term in important_terms)
        if impact not in {'High', 'Medium'} and not keyword_hit:
            continue
        score = (2 if impact == 'High' else 1) + (2 if keyword_hit else 0)
        scored.append({'title': title, 'dt': dt, 'impact': impact, 'score': score})
    scored.sort(key=lambda x: (-x['score'], x['dt']))
    return scored[:limit]


def get_premarket_snapshot(symbol, label):
    result = yahoo_chart(symbol, range_='5d', interval='1d', prepost=True)
    meta = result['meta']
    previous_close = float(meta.get('chartPreviousClose') or meta.get('previousClose') or 0.0)
    regular = float(meta.get('regularMarketPrice') or previous_close)
    pre = meta.get('preMarketPrice')
    post = meta.get('postMarketPrice')
    ref = pre if pre is not None else post if post is not None else regular
    ref = float(ref)
    move_pct = ((ref - previous_close) / previous_close) * 100 if previous_close else 0.0
    if move_pct > 0.15:
        direction = 'up'
    elif move_pct < -0.15:
        direction = 'down'
    else:
        direction = 'flat/mixed'
    return {
        'label': label,
        'symbol': symbol,
        'reference': ref,
        'previous_close': previous_close,
        'move_pct': move_pct,
        'direction': direction,
        'session': 'premarket' if pre is not None else 'postmarket' if post is not None else 'regular',
    }


def fmt_num(x):
    return f'{x:.2f}'


def build_desk_read(vix, spx, ndx, events):
    stances = []
    event_risk = any(e['impact'] == 'High' for e in events)
    if event_risk:
        stances.append('event risk elevated; do not overtrust early directional moves before scheduled data/speakers')
    if vix['pct_day'] >= 3:
        stances.append('volatility is expanding; tighten selectivity and avoid lazy chasing')
    elif vix['pct_day'] <= -3:
        stances.append('volatility is easing; cleaner continuation setups deserve more attention if opening structure confirms')
    else:
        stances.append('volatility is not screaming regime change; trade the tape, but stay selective')

    avg_move = (spx['move_pct'] + ndx['move_pct']) / 2.0
    if avg_move > 0.35:
        stances.append('premarket tone constructive; bullish leaders can earn more confidence if they hold after the open')
    elif avg_move < -0.35:
        stances.append('premarket tone soft; treat long-side leaders more skeptically unless price reclaims key levels cleanly')
    else:
        stances.append('premarket tone mixed; favor patience and confirmation over prediction')
    return stances[:3]


def render_markdown(payload):
    ts = payload['generated_at_mdt']
    lines = []
    lines.append('**BAZAAR OF FORTUNES — DAILY MACRO MARKET ANALYSIS**')
    lines.append(f"**Generated:** {ts} MDT")
    lines.append('')
    lines.append('**1. Overnight Drivers**')
    for item in payload['overnight_drivers']:
        lines.append(f"- {item['title']}")
    lines.append('')
    lines.append('**2. US Economic Calendar (Today / Tomorrow)**')
    for ev in payload['economic_calendar']:
        lines.append(f"- {ev['dt_label']} ET — {ev['title']} ({ev['impact']})")
    lines.append('')
    lines.append('**3. VIX Context**')
    v = payload['vix']
    lines.append(f"- VIX: {v['current']:.2f} vs yesterday {v['yesterday']:.2f} ({v['pct_day']:+.2f}%)")
    lines.append(f"- 5-session average: {v['week_avg']:.2f} | recent range: {v['recent_floor']:.2f}–{v['recent_ceiling']:.2f}")
    lines.append(f"- Read: {v['trend']}")
    lines.append('')
    lines.append('**4. Futures / Pre-Market Proxy**')
    for key in ['spx', 'ndx']:
        x = payload[key]
        lines.append(f"- {x['label']}: {x['direction']} {x['move_pct']:+.2f}% vs previous close ({x['session']})")
    lines.append('')
    lines.append('**5. Key Levels**')
    for lvl in payload['levels']:
        lines.append(
            f"- {lvl['symbol']}: prev H/L/C {lvl['high']:.2f}/{lvl['low']:.2f}/{lvl['close']:.2f} | pivot {lvl['pivot']:.2f} | S1 {lvl['s1']:.2f} | R1 {lvl['r1']:.2f}"
        )
    lines.append('')
    lines.append('**Desk Read / Synopsis**')
    for line in payload['desk_read']:
        lines.append(f'- {line}')
    return '\n'.join(lines).strip() + '\n'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()

    now = datetime.now()
    overnight = get_overnight_drivers(limit=3)
    econ = get_us_econ_events(limit=4)
    vix = get_vix_context()
    spx = get_premarket_snapshot('^GSPC', 'SPX / S&P 500 proxy')
    ndx = get_premarket_snapshot('^NDX', 'NDX / Nasdaq 100 proxy')
    levels = [chart_prev_day_levels('SPY'), chart_prev_day_levels('QQQ')]
    desk_read = build_desk_read(vix, spx, ndx, econ)

    payload = {
        'generated_at_iso': now.isoformat(),
        'generated_at_mdt': now.strftime('%Y-%m-%d %H:%M'),
        'overnight_drivers': [{'title': x['title'], 'link': x['link']} for x in overnight],
        'economic_calendar': [
            {
                'title': e['title'],
                'impact': e['impact'],
                'dt_label': e['dt'].strftime('%a %I:%M %p').lstrip('0'),
            }
            for e in econ
        ],
        'vix': vix,
        'spx': spx,
        'ndx': ndx,
        'levels': levels,
        'desk_read': desk_read,
    }
    markdown = render_markdown(payload)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(markdown, encoding='utf-8')
    JSON_PATH.write_text(json.dumps(payload, indent=2), encoding='utf-8')
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(markdown)


if __name__ == '__main__':
    main()
