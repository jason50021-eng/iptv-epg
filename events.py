#!/usr/bin/env python3
"""Add live game listings (NFL Sunday 7xx, NBA, NHL, ESPN+, NCAAF/NCAAB, FloSports, DAZN, soccer, PPV...) to guide.xml.gz.

Game Channels Update (Nov 7 2026): every US game slot always has a listing.
  - event with a time:    "Up next: X" until the start, then X, then "Ended: X"
  - event with no time:   X all day
  - finished, not renamed:"Ended: X"
  - empty slot:           "No event scheduled"
  - old-name protection:  each slot is also listed under its last 2 names (ids <slot>-prev1.ev, -prev2.ev),
    so a TiviMate channel list that is a few hours old still matches. History comes from the guide being
    updated, or from --history PREV_GUIDE (nightly build, whose fresh guide has no game channels yet).

The provider renames its game channels with the matchup and start time, e.g.
  'USA NBA 01: Atlanta Hawks vs Washington Wizards @ 07:00 PM EDT'
  'USA ESPN+ 016: Manhattan vs. Iona Nov 04 1:00PM ET (2026-11-04 13:00:05)'
This reads the current names from the provider and writes a guide block for each game.

Guide channel ids are stable per slot (nfl-sunday-705.ev), so a manual EPG pick in TiviMate keeps working
when the game changes; the display name is the channel's current name, so TiviMate can also match it automatically.

Usage:
  events.py GUIDE.xml.gz                 provider login from env IPTV_SERVER, IPTV_USER, IPTV_PASS
  events.py GUIDE.xml.gz --json FILE [--cats FILE] [--now ISO]   saved responses (testing)
  events.py GUIDE.xml.gz --history PREV_GUIDE.xml.gz              take old names from another guide
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
ANY_SLOT = re.compile(r'^([^:|]{1,45}?\d{1,3})\s*:\s*(.*)$')
# Groups whose numbered channels are game slots even without a "USA" prefix (Game Channels Update, Nov 7)
GAME_GROUPS = re.compile(r'^(PPV|Pay Per View|ESPN Events|Soccer Special|USA (NFL|NCAAF|NBA|WNBA|MLB|NHL)|'
                         r'Sport (NCAA|NJCAA|Lacrosse|College Baseball|Softball|Tennis|Golf|NBA G League|Rugby|'
                         r'Cycling|Handball)|Sports (DAZN|Motorsports)|CA: Sportsnet ?\+)', re.I)
LENGTH = [  # (pattern on slot name, minutes)
    (r'NCAAF', 210), (r'NFL', 195), (r'NCAAB|NCAAW|NJCAA|NBA|WNBA|Basketball', 150), (r'NHL|Sportsnet', 165),
    (r'MLB|Baseball|Softball', 185), (r'Soccer|Conmebol', 120), (r'PPV|UFC|Pay Per View', 240),
    (r'Cycling|Golf', 240), (r'ESPN\+|DAZN|Lacrosse', 150), (r'Flo', 180), (r'MOTORSPORT', 180),
]
CT = ZoneInfo('America/Chicago')
MONTHS = {m: i for i, m in enumerate('jan feb mar apr may jun jul aug sep oct nov dec'.split(), 1)}


def fetch_streams(action='get_live_streams'):
    server = os.environ['IPTV_SERVER'].rstrip('/')
    if not server.startswith('http'):
        server = 'http://' + server
    q = urllib.parse.urlencode({'username': os.environ['IPTV_USER'], 'password': os.environ['IPTV_PASS'],
                                'action': action})
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


def dated(now, month, day, hh, mm, ampm, tzname):
    """A start with month/day but no year: pick the year that puts it closest to now."""
    h = int(hh) % 12 + (12 if ampm.lower() == 'pm' else 0)
    tz = ZoneInfo(TZS.get((tzname or 'ET').upper(), 'America/New_York'))
    best = None
    for y in (now.year - 1, now.year, now.year + 1):
        try:
            t = datetime.datetime(y, month, day, h, int(mm), tzinfo=tz)
        except ValueError:
            continue
        if best is None or abs(t - now) < abs(best - now):
            best = t
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
    # '@ 6 Nov 07:00 PM ET'  (NCAAF, NCAAB, FloSports, DAZN, Sportsnet+)
    m = re.search(r'@\s*(\d{1,2})\s+([A-Za-z]{3})[a-z]*\s+(\d{1,2}):(\d{2})\s*([AaPp][Mm])\s*([A-Za-z]{2,3})?\s*$', rest)
    if m and m.group(2).lower() in MONTHS:
        start = dated(now, MONTHS[m.group(2).lower()], int(m.group(1)), m.group(3), m.group(4), m.group(5), m.group(6))
        return rest[:m.start()].strip(), start
    # '(11.6 7:00 PM ET)'  (Pay Per View)
    m = re.search(r'\((\d{1,2})\.(\d{1,2})\s+(\d{1,2}):(\d{2})\s*([AaPp][Mm])\s*([A-Za-z]{2,3})?\)\s*$', rest)
    if m:
        start = dated(now, int(m.group(1)), int(m.group(2)), m.group(3), m.group(4), m.group(5), m.group(6))
        return rest[:m.start()].strip(), start
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


def slot_of(name, group):
    """(slot, rest) when this channel is a game slot, else None."""
    m = SLOT.match(name)
    if m:
        return m.group(1).strip(), m.group(2)
    if GAME_GROUPS.match(group or ''):
        m = ANY_SLOT.match(name)
        if m:
            return m.group(1).strip(), m.group(2)
    return None


def build_events(streams, now, groups=None):
    """Return [(cid, name, [(start, stop, title, desc), ...])] with a listing for every game slot."""
    groups = groups or {}
    out, seen = [], set()
    hour = now.replace(minute=0, second=0, microsecond=0)
    day_end = hour + datetime.timedelta(hours=24)
    for c in streams:
        name = html.unescape(c.get('name') or '').strip()
        hit = slot_of(name, groups.get(str(c.get('category_id')), ''))
        if not hit or 'OCHO' in name.upper():
            continue
        slot, rest = hit
        cid = slug(slot)
        if cid in seen:
            n = 2
            while f'{cid[:-3]}-{n}.ev' in seen:
                n += 1
            cid = f'{cid[:-3]}-{n}.ev'
        seen.add(cid)
        title, start = parse(rest, now)
        blocks = []
        if not title:
            blocks.append((hour - datetime.timedelta(hours=1), day_end, 'No event scheduled',
                           'Nothing is scheduled on this channel right now.'))
        elif start is None:
            blocks.append((hour - datetime.timedelta(hours=1), day_end, title, 'Start time not listed by the provider.'))
        else:
            end = start + datetime.timedelta(minutes=length_for(slot))
            local = start.astimezone(CT).strftime('%a %-I:%M %p CT')
            ended = (f'Ended: {title}', f'Played {local}. Waiting for the provider to post the next event on this channel.')
            if end <= now:
                blocks.append((max(end, hour - datetime.timedelta(hours=1)), day_end) + ended)
            else:
                if start > now:
                    blocks.append((hour - datetime.timedelta(hours=1), start, f'Up next: {title}', f'Starts {local}.'))
                blocks.append((start, end, title, f'Live. Scheduled start {local}. End time is estimated.'))
                blocks.append((end, max(end + datetime.timedelta(hours=12), day_end)) + ended)
        out.append((cid, name, blocks))
    return out


def one_line(el):
    import xml.etree.ElementTree as ET
    el.tail = None
    return re.sub(r'>\s*\n\s*<', '><', ET.tostring(el, encoding='unicode')).replace('\n', ' ').strip()


def read_guide(path):
    """(non-game channel/programme lines, {game channel id: name}) from an existing guide."""
    import xml.etree.ElementTree as ET
    keep_ch, keep_pr, ev = [], [], {}
    if path and os.path.exists(path) and os.path.getsize(path):
        with gzip.open(path, 'rb') as f:
            for _, el in ET.iterparse(f):
                if el.tag == 'channel':
                    if el.get('id', '').endswith('.ev'):
                        ev[el.get('id')] = (el.findtext('display-name') or '').strip()
                    else:
                        keep_ch.append(one_line(el))
                elif el.tag == 'programme' and not el.get('channel', '').endswith('.ev'):
                    keep_pr.append(one_line(el))
    return keep_ch, keep_pr, ev


def merge(guide, slots, history=None):
    keep_ch, keep_pr, ev = read_guide(guide)
    if history:
        ev = {**read_guide(history)[2], **ev}
    import xml.etree.ElementTree as ET
    regular = {ET.fromstring(s).findtext('display-name') for s in keep_ch}
    current = {name for _, name, _ in slots}
    chans, progs, dropped, olds = [], [], 0, 0
    for cid, name, blocks in slots:
        if name in regular:  # same name as a regular channel: leave that one alone
            dropped += 1
            continue
        base = cid[:-3]
        names = [(cid, name)]
        hist = [ev.get(cid), ev.get(f'{base}-prev1.ev'), ev.get(f'{base}-prev2.ev')]
        for old in dict.fromkeys(h for h in hist if h and h != name and h not in current and h not in regular):
            if len(names) == 3:
                break
            names.append((f'{base}-prev{len(names)}.ev', old))
            olds += 1
        for i, n in names:
            chans.append(f'  <channel id={quoteattr(i)}><display-name>{escape(n)}</display-name></channel>\n')
            for s_, e_, title, desc in blocks:
                progs.append(f'  <programme start="{fmt(s_)}" stop="{fmt(e_)}" channel={quoteattr(i)}>'
                             f'<title lang="en">{escape(title)}</title><desc lang="en">{escape(desc)}</desc>'
                             f'<category lang="en">Sports</category></programme>\n')
    tmp = guide + '.tmp'
    with gzip.open(tmp, 'wt', encoding='utf-8', compresslevel=9) as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<tv generator-info-name="iptv-epg">\n')
        for s_ in keep_ch:
            f.write('  ' + s_ + '\n')
        f.writelines(chans)
        for s_ in keep_pr:
            f.write('  ' + s_ + '\n')
        f.writelines(progs)
        f.write('</tv>\n')
    os.replace(tmp, guide)
    print(f'kept {len(keep_ch)} channels; game slots with a listing: {len(slots) - dropped}, '
          f'old names kept: {olds}, skipped (same name as a regular channel): {dropped}')


if __name__ == '__main__':
    guide = sys.argv[1]
    now = datetime.datetime.now(UTC)
    arg = lambda k: sys.argv[sys.argv.index(k) + 1] if k in sys.argv else None
    groups = {}
    if arg('--json'):
        streams = json.load(open(arg('--json'), encoding='utf-8'))
        if arg('--cats'):
            groups = {str(c['category_id']): c['category_name'] for c in json.load(open(arg('--cats'), encoding='utf-8'))}
        if arg('--now'):
            now = datetime.datetime.fromisoformat(arg('--now'))
    else:
        if not all(os.environ.get(k) for k in ('IPTV_SERVER', 'IPTV_USER', 'IPTV_PASS')):
            print('IPTV_SERVER / IPTV_USER / IPTV_PASS secrets not set; skipping game listings')
            sys.exit(0)
        try:
            streams = fetch_streams()
        except Exception as e:  # provider down or blocking: keep the guide as it is
            print(f'could not read channel list from provider: {type(e).__name__}')
            sys.exit(0)
        try:
            groups = {str(c['category_id']): c['category_name'] for c in fetch_streams('get_live_categories')}
        except Exception as e:  # without group names only "USA ..." slots are recognised, as before
            print(f'could not read channel groups from provider: {type(e).__name__}')
    slots = build_events(streams, now, groups)
    for cid, name, blocks in slots:
        for s_, e_, t, d in blocks:
            if not t.startswith(('Up next', 'Ended', 'No event')) and s_ > now - datetime.timedelta(hours=4):
                print(f'  {s_.astimezone(CT):%a %-I:%M %p} {cid:24} {t}')
    merge(guide, slots, arg('--history'))
