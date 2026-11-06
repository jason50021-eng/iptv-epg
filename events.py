#!/usr/bin/env python3
"""Add live game listings (NFL Sunday 7xx, NBA, NHL, ESPN+, soccer, PPV...) to guide.xml.gz.

The provider renames its game channels with the matchup and start time, e.g.
  'USA NBA 01: Atlanta Hawks vs Washington Wizards @ 07:00 PM EDT'
  'USA ESPN+ 016: Manhattan vs. Iona Nov 04 1:00PM ET (2026-11-04 13:00:05)'
This reads the current names from the provider and writes a guide block for each game.

Guide channel ids are stable per slot (nfl-sunday-705.ev), so a manual EPG pick in TiviMate keeps working
when the game changes; the display name is the channel's current name, so TiviMate can also match it automatically.

Usage:
  events.py GUIDE.xml.gz                 provider login from env IPTV_SERVER, IPTV_USER, IPTV_PASS
  events.py GUIDE.xml.gz --json FILE     use a saved get_live_streams response (testing)
"""
import sys, os, re, json, gzip, html, datetime, urllib.request, urllib.parse
from zoneinfo import ZoneInfo
from xml.sax.saxutils import escape, quoteattr

UTC = datetime.timezone.utc
ET = ZoneInfo('America/New_York')
TZS = {'ET': 'America/New_York', 'EDT': 'America/New_York', 'EST': 'America/New_York',
       'CT': 'America/Chicago', 'CDT': 'America/Chicago', 'CST': 'America/Chicago',
       'MT': 'America/Denver', 'MDT': 'America/Denver', 'MST': 'America/Denver',
       'PT': 'America/Los_Angeles', 'PDT': 'America/Los_Angeles', 'PST': 'America/Los_Angeles'}
SLOT = re.compile(r'^(USA\s+[^:]{0,40}?(?:\d{1,3}|Night))\s*:\s*(.*)$')
LENGTH = [  # (pattern on slot name, minutes)
    (r'NFL', 195), (r'NBA|WNBA', 150), (r'NHL', 165), (r'MLB', 185), (r'Soccer|Conmebol', 120),
    (r'PPV|UFC', 240), (r'Cycling', 240), (r'ESPN\+', 150),
]


def fetch_streams():
    server = os.environ['IPTV_SERVER'].rstrip('/')
    if not server.startswith('http'):
        server = 'http://' + server
    q = urllib.parse.urlencode({'username': os.environ['IPTV_USER'], 'password': os.environ['IPTV_PASS'],
                                'action': 'get_live_streams'})
    req = urllib.request.Request(f'{server}/player_api.php?{q}', headers={'User-Agent': 'TiviMate/5.1.6'})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def slug(s):
    return re.sub(r'[^a-z0-9]+', '-', re.sub(r'^USA\s+', '', s).lower()).strip('-') + '.ev'


def length_for(slot):
    for rx, mins in LENGTH:
        if re.search(rx, slot, re.I):
            return mins
    return 180


def pick_day(clock, tz, now):
    """Names carry a clock time but no date: use the day that puts the start nearest to now (-8h..+20h)."""
    local_now = now.astimezone(tz)
    best = None
    for delta in (-1, 0, 1):
        day = (local_now + datetime.timedelta(days=delta)).date()
        start = datetime.datetime.combine(day, clock, tzinfo=tz)
        diff = (start - now).total_seconds() / 3600
        if -8 <= diff <= 20 and (best is None or abs(diff) < abs((best - now).total_seconds() / 3600)):
            best = start
    return best


def parse(rest, now):
    """Return (title, start datetime or None)."""
    rest = html.unescape(rest).strip()
    if not rest:
        return None, None
    # ESPN+ style: '... (2026-11-04 13:00:05)'  (Eastern time)
    m = re.search(r'\((\d{4}-\d{2}-\d{2} \d{2}:\d{2})(?::\d{2})?\)\s*$', rest)
    if m:
        start = datetime.datetime.strptime(m.group(1), '%Y-%m-%d %H:%M').replace(tzinfo=ET)
        title = rest[:m.start()].strip()
        title = re.sub(r'\s+[A-Z][a-z]{2} \d{1,2} \d{1,2}:\d{2}\s*[AP]M\s*[A-Z]{1,3}T?$', '', title)  # 'Nov 04 1:00PM ET'
        inner = re.search(r'\s*\(([^()]*)\)$', title)
        if inner and inner.group(1) in title[:inner.start()]:
            title = title[:inner.start()]  # 'Field Hockey: A vs B (A vs B)' -> drop the repeat
        return title.strip(), start
    # '@ 07:00 PM EDT' / '@ 10:00 pm'
    m = re.search(r'@\s*(\d{1,2}):(\d{2})\s*([AaPp][Mm])\s*([A-Za-z]{2,3})?\s*$', rest)
    if m:
        h, mi = int(m.group(1)) % 12, int(m.group(2))
        if m.group(3).lower() == 'pm':
            h += 12
        tz = ZoneInfo(TZS.get((m.group(4) or 'ET').upper(), 'America/New_York'))
        start = pick_day(datetime.time(h, mi), tz, now)
        return rest[:m.start()].strip(), start
    return rest, None


def fmt(t):
    return t.astimezone(UTC).strftime('%Y%m%d%H%M%S +0000')


def build_events(streams, now):
    channels, programmes = [], []
    seen = set()
    for c in streams:
        name = html.unescape(c.get('name') or '').strip()
        m = SLOT.match(name)
        if not m or 'OCHO' in name.upper():
            continue
        slot, rest = m.group(1).strip(), m.group(2)
        cid = slug(slot)
        if cid in seen:
            continue
        seen.add(cid)
        title, start = parse(rest, now)
        if not title:
            continue  # empty slot, nothing scheduled
        channels.append((cid, name))
        if start is None:  # title but no time: show it for the next 12 hours
            s, e = now.replace(minute=0, second=0, microsecond=0), None
            e = s + datetime.timedelta(hours=12)
            programmes.append((cid, s, e, title, 'Live event'))
            continue
        end = start + datetime.timedelta(minutes=length_for(slot))
        if end < now - datetime.timedelta(hours=1):
            continue  # stale name from a finished game
        local = start.astimezone(ZoneInfo('America/Chicago')).strftime('%-I:%M %p CT')
        pre = max(start - datetime.timedelta(hours=6), now - datetime.timedelta(hours=1))
        if pre < start:
            programmes.append((cid, pre, start, f'Up next: {title}', f'Starts at {local}.'))
        programmes.append((cid, start, end, title, f'Live. Scheduled start {local}. End time is estimated.'))
    return channels, programmes


def one_line(el):
    import xml.etree.ElementTree as ET
    el.tail = None
    return re.sub(r'>\s*\n\s*<', '><', ET.tostring(el, encoding='unicode')).replace('\n', ' ').strip()


def merge(guide, channels, programmes):
    keep_ch, keep_pr = [], []
    if os.path.exists(guide):
        import xml.etree.ElementTree as ET
        with gzip.open(guide, 'rb') as f:
            for _, el in ET.iterparse(f):
                if el.tag == 'channel' and not el.get('id', '').endswith('.ev'):
                    keep_ch.append(one_line(el))
                elif el.tag == 'programme' and not el.get('channel', '').endswith('.ev'):
                    keep_pr.append(one_line(el))
    tmp = guide + '.tmp'
    with gzip.open(tmp, 'wt', encoding='utf-8', compresslevel=9) as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<tv generator-info-name="iptv-epg">\n')
        for s in keep_ch:
            f.write('  ' + s + '\n')
        for cid, name in channels:
            f.write(f'  <channel id={quoteattr(cid)}><display-name>{escape(name)}</display-name></channel>\n')
        for s in keep_pr:
            f.write('  ' + s + '\n')
        for cid, s, e, title, desc in programmes:
            f.write(f'  <programme start="{fmt(s)}" stop="{fmt(e)}" channel={quoteattr(cid)}>'
                    f'<title lang="en">{escape(title)}</title><desc lang="en">{escape(desc)}</desc>'
                    f'<category lang="en">Sports</category></programme>\n')
        f.write('</tv>\n')
    os.replace(tmp, guide)
    print(f'kept {len(keep_ch)} channels; game channels with a listing: {len(channels)}, blocks: {len(programmes)}')


if __name__ == '__main__':
    guide = sys.argv[1]
    now = datetime.datetime.now(UTC)
    if '--json' in sys.argv:
        streams = json.load(open(sys.argv[sys.argv.index('--json') + 1], encoding='utf-8'))
        if '--now' in sys.argv:
            now = datetime.datetime.fromisoformat(sys.argv[sys.argv.index('--now') + 1])
    else:
        if not all(os.environ.get(k) for k in ('IPTV_SERVER', 'IPTV_USER', 'IPTV_PASS')):
            print('IPTV_SERVER / IPTV_USER / IPTV_PASS secrets not set; skipping game listings')
            sys.exit(0)
        try:
            streams = fetch_streams()
        except Exception as e:  # provider down or blocking: keep the guide as it is
            print(f'could not read channel list from provider: {type(e).__name__}')
            sys.exit(0)
    ch, pr = build_events(streams, now)
    for cid, s, e, t, d in pr:
        if not t.startswith('Up next'):
            print(f'  {s.astimezone(ZoneInfo("America/Chicago")):%a %-I:%M %p} {cid:24} {t}')
    merge(guide, ch, pr)
