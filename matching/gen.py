"""Write mapping.json, sources/*.channels.xml, manual-fixes.txt and no-guide.txt from match results.

OUT (env MATCH_OUT) is the repo root. shared-ids.txt in this folder lists provider guide IDs that are
shared by different stations; those IDs are not published, so each channel is matched by its own name.
"""
import json, re, collections, os, html, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import match as M

OUT = os.environ.get('MATCH_OUT', os.path.join(M.HERE, '..'))
os.makedirs(OUT + '/sources', exist_ok=True)

def read_list(name):
    p = os.path.join(M.HERE, name)
    if not os.path.exists(p):
        return set()
    return {l.split('#')[0].strip() for l in open(p) if l.split('#')[0].strip()}

SHARED_IDS = read_list('shared-ids.txt')
DROP_ALL_SHARED = 'ALL' in SHARED_IDS

# Descriptions matter for a useful guide: tvpassport (has descriptions) first, tvtv.us second.
SITE_PR = {'tvpassport.com': 1, 'ontvtonight.com': 2, 'directv.com': 3, 'tvinsider.com': 3, 'tvguide.com': 3,
           'i.mjh.nz': 4, 'plex.tv': 5, 'pluto.tv': 5, 'xumo.tv': 5, 'distro.tv': 5}

def compact(n):
    return re.sub(r'[^a-z0-9]', '', M.norm(n, strict=True))

by_compact = collections.defaultdict(list)
for _s in M.src:
    by_compact[compact(_s['name'])].append(_s)

def west_of(s):
    return M.is_west(s['name']) or s['xmltv_id'].endswith(('@West', '@Pacific'))

def alternatives(x, s):
    """All sources showing the same channel/feed as s, best first, max one per site."""
    alts = []
    c, sub = M.src_calls(s['name'])
    if c:
        alts = list(M.calls_idx.get((c, sub), []))
    else:
        base = s['xmltv_id'].split('@')[0] if s['xmltv_id'] else None
        alts = list(M.src_by_strict.get(M.norm(s['name'], strict=True), []))
        alts += by_compact.get(compact(s['name']), [])
        if base:
            alts += M.src_by_base.get(base, [])
        w = west_of(s)
        alts = [a for a in alts if west_of(a) == w]
        # for East feeds keep explicit-East or feedless names only
    if s not in alts:
        alts.append(s)
    best = {}
    for a in sorted(alts, key=lambda a: (SITE_PR.get(a['site'], 9), 0 if 'HD' in a['name'] else 1)):
        best.setdefault(a['site'], a)
    out = sorted(best.values(), key=lambda a: SITE_PR.get(a['site'], 9))[:3]
    return out

rows = json.load(open(os.path.join(M.WORK, 'match.json')))

src_keys = {}  # (site, site_id) -> key
def skey(s):
    k = (s['site'], s['site_id'])
    if k not in src_keys:
        src_keys[k] = dict(key='S%04d' % (len(src_keys) + 1), **{f: s[f] for f in ('site', 'site_id', 'name', 'lang')})
    return src_keys[k]['key']

matched = [x for x in rows if x['src']]
for x in matched:
    x['cands'] = alternatives(x, x['src'])
    x['shift'] = x['src'].get('shift', 0)
    call = M.src_calls(x['cands'][0]['name'])[0] or ''
    x['feedkey'] = (M.norm(x['cands'][0]['name'], strict=True), x['shift'], west_of(x['src']), call)

# Decide which channels can keep the provider's guide ID (no conflict) and which need their own entry.
grp = collections.defaultdict(list)
for x in matched:
    if x['epg']:
        grp[x['epg']].append(x)
owner = {}
for pid, xs in grp.items():
    own = None
    for x in xs:
        mm = re.match(r'(?:call|city|override):([A-Z]+)', x['how'])
        if mm and mm.group(1).lower() in pid.lower():
            own = x['feedkey']; break
    if not own:
        own = collections.Counter(x['feedkey'] for x in xs).most_common(1)[0][0]
    owner[pid] = own

def same_feed(a, b):
    if a[1] != b[1] or a[2] != b[2] or a[3] != b[3]:
        return False
    return a[0] == b[0] or M.sim(a[0], b[0]) >= 0.8

def slug(n):
    n = re.sub(r'^USA\s+', '', html.unescape(n))
    return re.sub(r'[^a-z0-9]+', '-', n.lower()).strip('-') + '.jm'

# provider IDs used by more than one station (KYTV carries WWLP's ID, for example)
conflicted = {x['epg'] for x in matched if x['epg'] and not same_feed(x['feedkey'], owner[x['epg']])}
drop = (conflicted if DROP_ALL_SHARED else set()) | (SHARED_IDS - {'ALL'})

mapping = {}
stats = collections.Counter()
fixlist = []
for x in matched:
    if x['epg'] in drop:
        oid, kind = slug(x['name']), 'shared'  # matched by name in TiviMate
    elif x['epg'] and same_feed(x['feedkey'], owner[x['epg']]):
        oid, kind = x['epg'], 'id'
    else:
        oid, kind = slug(x['name']), ('name' if not x['epg'] else 'fix')
        if kind == 'fix':
            fixlist.append(x)
    stats[kind] += 1
    if oid in mapping:
        continue
    mapping[oid] = dict(id=oid, name=html.unescape(x['name']).strip(), shift=x['shift'],
                        src=[skey(s) for s in x['cands']])

json.dump(sorted(mapping.values(), key=lambda m: m['name']), open(OUT + '/mapping.json', 'w'), indent=1)

groups = {'tvpassport': ['tvpassport.com'], 'ontvtonight': ['ontvtonight.com'], 'other': None}
for g, sites in groups.items():
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<channels>']
    n = 0
    for v in src_keys.values():
        if (sites and v['site'] in sites) or (not sites and v['site'] not in ('tvpassport.com', 'ontvtonight.com')):
            lines.append('  <channel site="%s" site_id="%s" lang="%s" xmltv_id="%s">%s</channel>' % (
                html.escape(v['site']), html.escape(v['site_id']), v['lang'] or 'en', v['key'], html.escape(v['name'])))
            n += 1
    lines.append('</channels>')
    open(f'{OUT}/sources/{g}.channels.xml', 'w').write('\n'.join(lines) + '\n')
    print(g, n, 'sources')

print('channels:', dict(stats), 'guide entries:', len(mapping))
unmatched = sorted(x['name'] for x in rows if x['how'] == 'none')
with open(os.path.join(OUT, 'manual-fixes.txt'), 'w') as f:
    f.write("These channels carry a guide ID that the provider also uses for a DIFFERENT station or the East feed,\n"
            "so TiviMate links them to the wrong listings. Fix any you watch once: in TiviMate open the channel's\n"
            "options, choose the TV guide / EPG channel, and pick the entry with the same name from this guide.\n\n")
    f.write('\n'.join(sorted(x['name'] for x in fixlist)) + '\n')
with open(os.path.join(OUT, 'no-guide.txt'), 'w') as f:
    f.write("No free guide source carries these channels (Music Choice video channels, rotating Starzplay / ViX /\n"
            "TUDN / Conmebol slots, public-access stations, some streaming-only and regional sports channels).\n\n")
    f.write('\n'.join(unmatched) + '\n')
json.dump({'entries': len(mapping), 'kinds': dict(stats), 'unmatched': len(unmatched), 'dropped_ids': sorted(drop)},
          open(os.path.join(M.WORK, 'summary.json'), 'w'), indent=1)
print('fix:', len(fixlist), 'unmatched:', len(unmatched), 'shared ids dropped:', len(drop))
