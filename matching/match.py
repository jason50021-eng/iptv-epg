"""Match the provider's US channels to free guide sources (iptv-org/epg site channel lists).

Paths come from environment variables so the same code runs in GitHub Actions:
  EPG_SITES   iptv-org/epg "sites" folder           IPTV_ORG_DB  iptv-org database channels.csv
  CHANNELS    channels.json from channels.py         MATCH_WORK   folder for intermediate files
"""
import json, re, csv, html, glob, collections, sys, os
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.environ.get('MATCH_WORK', os.path.join(HERE, '..', 'work'))
SITES = os.environ.get('EPG_SITES', os.path.join(HERE, '..', 'epg', 'sites'))
DB_CSV = os.environ.get('IPTV_ORG_DB', os.path.join(WORK, 'channels.csv'))
CHANNELS = os.environ.get('CHANNELS', os.path.join(HERE, '..', 'channels.json'))
os.makedirs(WORK, exist_ok=True)
BASE = WORK  # kept for gen.py

# ---------- sources ----------
# tvtv.us and streamingtvguides.com returned nothing from GitHub's servers (first run, Nov 5), so they are not used.
SRC_FILES = [  # (glob, priority) lower = preferred
    ('tvpassport.com/tvpassport.com.channels.xml', 1),
    ('ontvtonight.com/ontvtonight.com_us.channels.xml', 2),
    ('tvguide.com/tvguide.com.channels.xml', 3),
    ('directv.com/directv.com.channels.xml', 3),
    ('tvinsider.com/tvinsider.com.channels.xml', 3),
    ('i.mjh.nz/i.mjh.nz_pluto.channels.xml', 4),
    ('i.mjh.nz/i.mjh.nz_samsung.channels.xml', 4),
    ('i.mjh.nz/i.mjh.nz_roku.channels.xml', 4),
    ('i.mjh.nz/i.mjh.nz_plex.channels.xml', 4),
    ('i.mjh.nz/i.mjh.nz_pbs.channels.xml', 4),
    ('pluto.tv/pluto.tv_us.channels.xml', 5),
    ('plex.tv/plex.tv_us.channels.xml', 5),
    ('xumo.tv/xumo.tv.channels.xml', 5),
    ('distro.tv/distro.tv.channels.xml', 5),
]
src = []

# epgshare01 publishes whole-country files (one download each). Its file names and channel IDs change, so the
# build downloads the current channel lists (epg_ripper_<TAG>.txt) into EPGSHARE_LISTS and matches against those.
EPGSHARE_TAGS = {'US2': 3, 'US_SPORTS1': 3, 'FANDUEL1': 3, 'US_LOCALS1': 3, 'PLEX1': 4, 'DISTROTV1': 4}
EPGSHARE_LISTS = os.environ.get('EPGSHARE_LISTS', os.path.join(WORK, 'epgshare'))

def epgshare_name(cid):
    n = html.unescape(cid)
    n = re.sub(r'\.(us\d*|us_locals\d*|plex|distro|[a-z]{2}\d?)$', '', n, flags=re.I)
    n = re.sub(r'^plex\.tv\.', '', n, flags=re.I)
    n = n.replace('.', ' ').strip()
    if ' ' not in n and re.search(r'[a-z][A-Z]', n):  # "MLB-SeattleMariners" -> "MLB - Seattle Mariners"
        n = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', n).replace('-', ' - ')
    return n

for tag, pr in EPGSHARE_TAGS.items():
    path = os.path.join(EPGSHARE_LISTS, tag + '.txt')
    if not os.path.exists(path):
        continue
    for line in open(path, encoding='utf-8', errors='ignore'):
        cid = line.strip()
        if not cid or cid.startswith('--') or re.fullmatch(r'\d{12}', cid):
            continue
        src.append(dict(site='epgshare01.online', site_id=f'{tag}#{html.unescape(cid)}', xmltv_id='', lang='en',
                        name=epgshare_name(cid), pr=pr))

for f, pr in SRC_FILES:
    for p in glob.glob(f'{SITES}/{f}'):
        for ch in ET.parse(p).getroot():
            site_id = ch.get('site_id')
            if (ch.get('lang') or 'en') not in ('en', 'es'):
                continue  # e.g. Al Jazeera Arabic
            if ch.get('site') == 'i.mjh.nz' and not re.search(r'/us\b|/us#|_us|us\.xml', site_id, re.I):
                continue
            src.append(dict(site=ch.get('site'), site_id=site_id, xmltv_id=ch.get('xmltv_id') or '',
                            lang=ch.get('lang'), name=html.unescape(ch.text or '').strip(), pr=pr))

def is_west(n):
    return bool(re.search(r'\b(west|pacific|westcoast)\b', n, re.I))

STRICT_STOP = {'uhd', 'lhd', 'fhd', 'hd', 'sd', '4k', '1080', '1080p', '720', '720p', 'backup', 'east', 'eastern',
        'west', 'pacific', 'feed', 'este', 'oeste', 'live', 'hevc', 'raw', 'us', 'usa'}
STOP = {'uhd', 'lhd', 'fhd', 'hd', 'sd', '4k', '1080', '1080p', '720', '720p', 'backup', 'east', 'eastern',
        'west', 'pacific', 'feed', 'channel', 'tv', 'network', 'the', 'ld', 'este', 'oeste', 'us', 'live', 'hevc', 'raw'}
ALIAS = {
    'fox sports 1': 'fs1', 'fox sports 2': 'fs2', 'fs 1': 'fs1', 'fs 2': 'fs2',
    'a and e': 'aande', 'ae': 'aande', 'hgtv': 'hgtv', 'home and garden': 'hgtv',
    'espn 2': 'espn2', 'espn u': 'espnu', 'c span': 'cspan', 'c span 2': 'cspan2', 'c span 3': 'cspan3',
    'nickelodeon': 'nick', 'nick jr': 'nickjr', 'tbs': 'tbs', 'trutv': 'trutv', 'tru': 'trutv',
    'nat geo': 'national geographic', 'natgeo': 'national geographic', 'nat geo wild': 'national geographic wild',
    'investigation discovery': 'id', 'id investigation discovery': 'id', 'msnbc': 'ms now',
    'fox news': 'fox news', 'fnc': 'fox news', 'cnbc': 'cnbc', 'tcm': 'turner classic movies',
    'hln': 'hln', 'ifc': 'ifc', 'ovation': 'ovation', 'wetv': 'we', 'we': 'we',
    'nbcsn': 'nbc sports', 'golf': 'golf', 'nbc golf': 'golf', 'mlb': 'mlb', 'nhl': 'nhl',
    'cbs sports': 'cbs sports', 'starz encore': 'encore', 'bet her': 'bether', 'syfy': 'syfy',
    'discovery': 'discovery', 'disney': 'disney', 'disney jr': 'disney junior', 'disney xd': 'disney xd',
    'paramount': 'paramount', 'paramount network': 'paramount', 'cartoon': 'cartoon',
    'tv land': 'land', 'tvland': 'land', 'oxygen true crime': 'oxygen', 'reelz': 'reelz',
    'hallmark movies and mysteries': 'hallmark mystery', 'hallmark movies mysteries': 'hallmark mystery',
    'hmm': 'hallmark mystery', 'hallmark drama': 'hallmark family', 'game show': 'gsn', 'game show west': 'gsn',
    'ahc': 'american heroes', 'american heroes': 'american heroes', 'msgsn': 'msg', 'cbsn bay area': 'cbs news bay area', 'cbsn los angeles': 'cbs news los angeles', 'msg 2 plus': 'msg plus 2',
    'bein sports enespanol': 'bein sports en espanol', 'oprah winfrey own': 'own', 'fxm': 'fx movie',
    'nbc golf': 'golf', 'nbc sport': 'nbc sports', 'wgn 9 chicago': 'wgn america',
    'epix': 'mgm plus', 'epix hits': 'mgm plus hits', 'epix2': 'mgm plus marquee', 'epix 2': 'mgm plus marquee',
    'epix drive in': 'mgm plus drive in', 'sony movie': 'sony movies', 'sony movies': 'sony movies',
    'tennis': 'tennis', 'golazo': 'cbs sports golazo', 'fox weather': 'fox weather',
}

def norm(n, provider=False, strict=False):
    n = html.unescape(n).lower()
    if provider:
        n = re.sub(r'^(usa|uss|us:?)\s+', '', n)
        n = re.sub(r'^\(latin\)\s*|^latin\s+', '', n)
    n = re.sub(r'\bcbsn\b', 'cbs news', n)
    n = re.sub(r'\bspectrum news (1|one)\b', 'spectrum news', n)
    n = re.sub(r'\bspectrum news mo st louis\b', 'spectrum news st louis', n)
    n = n.replace('&', ' and ').replace('+', ' plus ').replace("'", '')
    n = re.sub(r'\(.*?\)', ' ', n)
    n = re.sub(r'[^a-z0-9 ]', ' ', n)
    n = re.sub(r'\b(\d+)\s*(p)\b', '', n)
    toks = [t for t in n.split() if t not in (STRICT_STOP if strict else STOP)]
    s = ' '.join(toks)
    return s if strict else ALIAS.get(s, s)

def sim(a, b):
    import difflib
    return difflib.SequenceMatcher(None, a, b).ratio()

# ---------- iptv-org database ----------
db = {}
for r in csv.DictReader(open(DB_CSV, encoding='utf-8')):
    db[r['id']] = r
db_lower = {k.lower(): k for k in db}
name2ids = collections.defaultdict(set)
name2ids_strict = collections.defaultdict(set)
for k, r in db.items():
    if r['closed']:
        continue
    for nm in [r['name']] + [a for a in r['alt_names'].split(';') if a]:
        name2ids[norm(nm)].add(k)
        name2ids_strict[norm(nm, strict=True)].add(k)

src_by_base = collections.defaultdict(list)   # iptv-org id -> sources
src_by_norm = collections.defaultdict(list)
src_by_strict = collections.defaultdict(list)
for s in src:
    if s['xmltv_id']:
        src_by_base[s['xmltv_id'].split('@')[0]].append(s)
    src_by_norm[norm(s['name'])].append(s)
    src_by_strict[norm(s['name'], strict=True)].append(s)

def pick(cands, west):
    cands = [c for c in (cands or []) if 'PAC-12' not in c['name'].upper()]
    if not cands:
        return None
    def key(s):
        feedpen = 0
        sw = is_west(s['name']) or s['xmltv_id'].endswith('@West') or s['xmltv_id'].endswith('@Pacific')
        if sw != west:
            feedpen = 10
        hdpen = 0 if re.search(r'\bHD\b|@HD', s['name'] + s['xmltv_id']) else 0.5
        return (feedpen, s['pr'], hdpen)
    best = sorted(cands, key=key)[0]
    sw = is_west(best['name']) or best['xmltv_id'].endswith(('@West', '@Pacific'))
    if west and not sw:
        best = dict(best, shift=180)  # West feed: same schedule 3 hours later
    return best

# ---------- locals ----------
CALL_RE = re.compile(r'\b([KW][A-Z]{2,3})(?:[- ]?(?:DT|TV|LD|CD|CA|LP|D)?(\d)?)?\b')
NOT_CALLS = {'WEST', 'WILD', 'WORLD', 'KIDS', 'WOMEN', 'WAPA_', 'WOW', 'WWE', 'KIDZ', 'WORD', 'WAR', 'KISS', 'WINE',
             'WIND', 'KING', 'KUNG', 'WIRE', 'WARS', 'WTF', 'KTV'}
LOCAL_CATS = {'598', '357', '353', '354', '356', '355', '536', '538'}
NETWORDS = r'\b(ABC|CBS|NBC|FOX|CW|PBS|MY|MYTV|ION|TELEMUNDO|UNIVISION|UNIMAS|IND|INDEPENDENT|MNTV)\b'

def src_calls(name):
    """Return (call, subchannel) parsed from a source local name like 'CW (KPLR-DT1) St Louis MO'."""
    m = re.search(r'\(([KW][A-Z]{2,3})(?:-?(?:DT|TV|LD|CD|CA|LP)?)?(\d)?(?:-?(?:DT|TV|LD|CD)?)?\)', name)
    if not m:
        b = re.fullmatch(r'([KW][A-Z]{2,3})(?:-(?:TV|DT|LD|CD))?', name.strip())
        if b and b.group(1) not in NOT_CALLS:
            return b.group(1), 1
        return None, None
    return m.group(1), int(m.group(2)) if m.group(2) else 1

calls_idx = collections.defaultdict(list)
for s in src:
    c, sub = src_calls(s['name'])
    if c:
        calls_idx[(c, sub)].append(s)

def provider_calls(name):
    out = []
    for m in CALL_RE.finditer(name.upper()):
        c = m.group(1)
        if c in NOT_CALLS:
            continue
        sub = int(m.group(2)) if m.group(2) else 1
        out.append((c, sub))
    return out

def match_local(c):
    up = c['name'].upper()
    net = re.search(NETWORDS, up)
    for call, sub in provider_calls(c['name']):
        cands = calls_idx.get((call, sub), [])
        if not cands:
            continue
        if net:  # prefer same network
            same = [s for s in cands if net.group(1) in s['name'].upper()]
            cands = same or cands
        return sorted(cands, key=lambda s: (s['pr'], 0 if 'HD' in s['name'] else 1))[0], f'call:{call}{sub}'
    return None, None

OVERRIDE_CALLS = [(r'\bNINE\b.*ST\.? ?LOUIS|ST\.? ?LOUIS.*\bNINE\b', 'KETC')]
NETMAP = {'MY': 'MY', 'MYTV': 'MY', 'MNTV': 'MY', 'MYNETWORKTV': 'MY'}
def match_city(c):
    up = c['name'].upper()
    for rx, call in OVERRIDE_CALLS:
        if re.search(rx, up):
            cands = calls_idx.get((call, 1), [])
            if cands:
                return sorted(cands, key=lambda s: s['pr'])[0], 'override:' + call
    m = re.search(NETWORDS, up)
    if not m:
        return None, None
    net = m.group(1)
    rest = re.sub(r'^USA\s+|\(LATIN\)|\bLATIN\b', ' ', up)
    rest = re.sub(NETWORDS + r'|\b(UHD|LHD|FHD|HD|SD|EAST|WEST|KIDS|PLUS|\d+)\b|[^A-Z ]', ' ', rest)
    city = [w for w in rest.split() if len(w) > 2]
    if not city:
        return None, None
    hits = {}
    for (call, sub), lst in calls_idx.items():
        if sub != 1:
            continue
        for s in lst:
            nm = s['name'].upper()
            netok = nm.startswith(net) or (net == 'MY' and nm.startswith(('MY', 'MNT')))
            if netok and all(w in re.sub(r'[^A-Z ]', ' ', nm).split() for w in city):
                hits.setdefault(call, []).append(s)
    if len(hits) == 1:
        call, lst = next(iter(hits.items()))
        return sorted(lst, key=lambda s: s['pr'])[0], 'city:' + call
    return None, None

# ---------- events ----------
EVENT_CATS = {'400', '398', '359', '360', '362', '335', '1011', '594'}
EVENT_RE = re.compile(r'(@|\b(NFL (Sunday|Monday|Thursday|Sunday Night))\b|\b(NBA|NHL|MLB|WNBA|PPV|Soccer|Cycling|NCAAF|NCAAB|MLS|ESPN\+|Peacock|Conmebol|ViX Deportes|Starzplay|DAZN)\s*\d+\s*:?)', re.I)

EVENT_SLOT = re.compile(r'^USA\s+[^:]{0,40}?(\d{1,3}|Night)\s*:')

def is_event(c):
    """Game/event slot channels whose name carries the event, e.g. 'USA NBA 01: Hawks vs Wizards @ 07:00 PM EDT'."""
    return bool(EVENT_SLOT.search(c['name'])) and 'OCHO' not in c['name'].upper()

# ---------- manual matches ----------
# (provider name pattern, source name pattern). Source names are compared lowercased with a trailing HD removed.
MANUAL = [
    (r'detroit sportsnet', r'^fanduel sports network detroit$'),
    (r'diamondbac', r'^arizona diamondbacks tv$'),
    (r'\bt2 tennis\b', r'^tennis channel 2$'),
    (r'chicago sports network plus', r'^(chsn )?chicago sports network plus$'),
    (r'spectrum oc ?16', r'^spectrum oc 16$|^spectrum sports hawaii \(oc16\)$'),
    (r'mavtv select', r'^mavtv select$'),
    (r'mav ?tv', r'^mavtv motorsports$|^mavtv$'),
    (r'root sports northwest plus', r'^root sports northwest plus$'),
    (r'root sports northwest(?! plus)', r'^root sports northwest$'),
    (r'sportsnet la dodgers|sportsnet dodgers', r'^spectrum sportsnet (la )?dodgers$|^spectrum sportsnet la$'),
    (r'sportsnet lakers', r'^spectrum sportsnet lakers$'),
    (r'\bmasn ?2\b', r'^masn ?2$'),
    (r'\bqvc ?3\b', r'^qvc ?3$'),
    (r'\bfe ?tv\b', r'^fetv \(family entertainment television\)$|^fetv$'),
    (r'axs tv now', r'^axs tv now$'),
    (r'pokergo', r'^pokergo$'),
    (r'bon ?app', r'^bon app[eé]tit( tv)?$'),
    (r'history military', r'^military heroes presented by history$'),
    (r'discovery science', r'^science( channel)?$'),
    (r'boxing tv', r'^boxing tv$'),
    (r'edgesport', r'^edgesport$'),
    (r'gulf coast sports', r'^wala gulf coast sports & entertainment network$'),
    (r'\bnhra\b', r'^nhra tv$'),
]
def _srcname(s):
    n = html.unescape(html.unescape(s['name'])).lower().strip()
    return re.sub(r'\s+(hd|hdtv|uhd)$', '', n)

def match_manual(c):
    n = re.sub(r'^(usa|us:?)\s+', '', html.unescape(c['name']).lower())
    for prx, srx in MANUAL:
        if re.search(prx, n):
            cands = [s for s in src if re.search(srx, _srcname(s))]
            s = pick(cands, is_west(c['name']))
            if s:
                return s, 'manual'
    return None, None


# ---------- main ----------
def match(c):
    if is_event(c):
        return None, 'event'
    s, how = match_manual(c)
    if s:
        return s, how
    west = is_west(c['name'])
    if 'PBS KIDS' not in c['name'].upper() and (c['category_id'] in LOCAL_CATS or re.search(NETWORDS + r'.*\b[KW][A-Z]{2,3}\b', c['name'].upper())):
        s, how = match_local(c)
        if s:
            return s, how
    nn = norm(c['name'], provider=True)
    ns = norm(c['name'], provider=True, strict=True)
    def ok(srcrec):  # sanity: source name must resemble the provider name
        a, b = norm(srcrec['name'], strict=True), ns
        return sim(a, b) >= 0.6 or a in b or b in a or norm(srcrec['name']) == nn  # alias/renamed match
    # 1) provider epg id -> iptv-org id (trusted)
    pid = (c['epg_channel_id'] or '').lower()
    if pid.endswith('.us') and pid in db_lower:
        s = pick(src_by_base.get(db_lower[pid], []), west)
        if s and ok(s):
            return s, 'id:' + db_lower[pid]
    # 2) exact strict name against sources, then iptv-org names
    s = pick(src_by_strict.get(ns, []), west)
    if s:
        return s, 'name'
    for table, key in ((name2ids_strict, ns), (name2ids, nn)):
        for i in sorted(table.get(key, ())):
            if db[i]['country'] != 'US':
                continue
            s = pick(src_by_base.get(i, []), west)
            if s and ok(s):
                return s, 'id:' + i
    # 3) loose name
    s = pick(src_by_norm.get(nn, []), west)
    if s and ok(s):
        return s, 'name'
    # 3b) PBS Kids local feeds -> national PBS Kids schedule
    if 'PBS KIDS' in c['name'].upper():
        s = pick(src_by_strict.get('pbs kids', []), False)
        if s:
            return s, 'name:pbskids'
    # 4) local call-sign fallback, then network+city
    s, how = match_local(c)
    if s:
        return s, how
    s, how = match_city(c)
    if s:
        return s, how
    return None, 'none'

def load_channels(path):
    data = json.load(open(path, encoding='utf-8'))
    if isinstance(data, dict) and 'channels' in data:  # channels.json written by channels.py
        return [dict(name=c['name'], epg_channel_id=c.get('epg_id'), category_id=str(c['group']),
                     stream_id=c.get('stream_id')) for c in data['channels']]
    return data  # raw get_live_streams response


if __name__ == '__main__':
    d = load_channels(CHANNELS)
    STATES = set('AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA LO ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA PR RI SC SD TN TX UT VT VA WA WV WI WY'.split())
    def is_us(n):
        m = re.match(r'^([A-Z]{2})(?:-[A-Z]{2})? ?\|', n)
        return n.startswith('USA') or bool(m and m.group(1) in STATES)
    # also unprefixed channels sitting in mostly-US groups ('NBC KYTV Springfield', 'US CW 4 (KRON) ...')
    bycat = collections.defaultdict(list)
    for c in d:
        bycat[c['category_id']].append(c)
    uscats = {k for k, v in bycat.items() if sum(is_us(c['name']) for c in v) / len(v) >= 0.6}
    us = [c for c in d if is_us(c['name']) or (c['category_id'] in uscats
          and not re.match(r'^(LA:|SUR|Latin)', c['name']))]
    res = []
    stat = collections.Counter()
    for c in us:
        s, how = match(c)
        stat[how.split(':')[0]] += 1
        res.append(dict(stream_id=c['stream_id'], name=c['name'], cat=c['category_id'], epg=c['epg_channel_id'],
                        how=how, src=s))
    json.dump(res, open(os.path.join(WORK, 'match.json'), 'w'), indent=0)
    print(stat, 'total', len(us))
