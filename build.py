#!/usr/bin/env python3
"""Build guide.xml.gz for the IPTV playlist.

Reads the raw guides grabbed from the free sources (channel ids S0001...), and writes one XMLTV
file whose channel ids / display names match the IPTV provider's channels, using mapping.json:
  id     - guide id TiviMate matches on (provider tvg-id, or our own id for channels without one)
  name   - exact channel name in the playlist (TiviMate matches on this when the id is missing)
  src    - source keys in priority order; the first one that returned programmes is used
  shift  - minutes to shift (West feeds built from an East schedule)

Usage: build.py OUTPUT.xml.gz RAW1.xml [RAW2.xml ...]
"""
import sys, json, gzip, os, re, datetime, collections
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape, quoteattr

HERE = os.path.dirname(os.path.abspath(__file__))
FMT = '%Y%m%d%H%M%S'


def shift_time(value, minutes):
    stamp, _, tz = value.partition(' ')
    t = datetime.datetime.strptime(stamp[:14], FMT) + datetime.timedelta(minutes=minutes)
    return t.strftime(FMT) + (' ' + tz if tz else '')


def add_artwork(el):
    """TiviMate shows a show's picture from <icon src>; the sources give it as <image>url</image>."""
    if el.find('icon') is None:
        img = (el.findtext('image') or '').strip()
        if img.startswith('http'):
            icon = ET.Element('icon', src=img)
            after = ('url', 'country', 'episode-num', 'video', 'audio', 'previously-shown', 'premiere',
                     'last-chance', 'new', 'subtitles', 'rating', 'star-rating', 'review', 'image')
            pos = next((i for i, c in enumerate(el) if c.tag in after), len(el))  # XMLTV element order
            el.insert(pos, icon)


def coverage_end(els):
    return max((e.get('stop') or e.get('start'))[:14] for e in els)


def pick_source(keys, progs):
    """Pick the source with the best coverage from 3 hours ago to 3 days ahead, preferring earlier
    (higher quality) sources when they are close. A source that skips today or only publishes a few
    hours ahead (Samsung TV Plus) loses to a backup that covers the whole window."""
    have = [k for k in keys if progs.get(k)]
    if not have:
        return None
    now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    lo, hi = now - datetime.timedelta(hours=3), now + datetime.timedelta(days=3)

    def hours(k):
        total = 0.0
        for e in progs[k]:
            try:
                a = datetime.datetime.strptime(e.get('start')[:14], FMT)
                b = datetime.datetime.strptime((e.get('stop') or e.get('start'))[:14], FMT)
            except (TypeError, ValueError):
                continue
            a, b = max(a, lo), min(b, hi)
            if b > a:
                total += (b - a).total_seconds() / 3600
        return total

    cover = {k: hours(k) for k in have}
    best = max(cover.values())
    return next(k for k in have if cover[k] >= best * 0.85 - 1)


def load_programmes(paths):
    progs = collections.defaultdict(list)
    for p in paths:
        if not os.path.exists(p) or os.path.getsize(p) == 0:
            print(f'skip missing {p}')
            continue
        opener = gzip.open if p.endswith('.gz') else open
        try:
            with opener(p, 'rb') as f:
                for _, el in ET.iterparse(f, events=('end',)):
                    if el.tag == 'programme':
                        ch = el.get('channel')
                        if el.find('title') is not None:
                            progs[ch].append(el)
                    elif el.tag == 'channel':
                        el.clear()
        except ET.ParseError as e:  # a broken source file must not kill the whole guide
            print(f'parse error in {p}: {e}')
    for ch in progs:
        progs[ch].sort(key=lambda e: e.get('start'))
    return progs


def calibrate_lineups(mapping, progs, index):
    """ontvtonight lists each market in its local time but the grabber reads every time as Eastern, so a Pacific
    station comes out 3 hours early. For each ontvtonight market lineup, compare its stations against tvpassport
    (which is right) and find the hour offset where the shows line up; then shift that lineup's programmes."""
    votes = collections.defaultdict(collections.Counter)
    for m in mapping:
        tp = [k for k in m['src'] if index.get(k, [''])[0] == 'tvpassport.com' and progs.get(k)]
        ot = [k for k in m['src'] if index.get(k, [''])[0] == 'ontvtonight.com' and progs.get(k)]
        if not tp or not ot:
            continue
        ref = {(e.findtext('title'), e.get('start')[:12]) for e in progs[tp[0]]}
        counts = {h: sum((e.findtext('title'), shift_time(e.get('start'), h * 60)[:12]) in ref for e in progs[ot[0]])
                  for h in range(-1, 7)}  # real US offsets from Eastern: Atlantic -1 ... Hawaii +5/+6
        best = max(counts, key=lambda h: (counts[h], -abs(h)))  # ties go to the smaller shift
        n0 = counts[0]
        # only trust a clear winner: shows that repeat every hour match at many shifts
        if best != 0 and counts[best] >= 3 and counts[best] >= n0 + 2:
            votes[index[ot[0]][1].split('/')[0]][best] += 1
        elif n0 >= 3:
            votes[index[ot[0]][1].split('/')[0]][0] += 1
    shifts = {lu: c.most_common(1)[0][0] for lu, c in votes.items() if c.most_common(1)[0][0] != 0}
    for k, (site, site_id, _) in index.items():
        h = shifts.get(site_id.split('/')[0]) if site == 'ontvtonight.com' else None
        if h and progs.get(k):
            for e in progs[k]:
                e.set('start', shift_time(e.get('start'), h * 60))
                if e.get('stop'):
                    e.set('stop', shift_time(e.get('stop'), h * 60))
    return shifts


def main(out, raws):
    mapping = json.load(open(os.path.join(HERE, 'mapping.json'), encoding='utf-8'))
    progs = load_programmes(raws)
    idx_path = os.path.join(HERE, 'sources', 'index.json')
    index = json.load(open(idx_path, encoding='utf-8')) if os.path.exists(idx_path) else {}
    shifts = calibrate_lineups(mapping, progs, index)
    print(f'ontvtonight market time fixes (hours): {len(shifts)} markets, '
          + ', '.join(f'{h:+d}h x{list(shifts.values()).count(h)}' for h in sorted(set(shifts.values()))))
    used, empty, n_prog = 0, [], 0
    cutoff = (datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) - datetime.timedelta(hours=3)).strftime(FMT)
    tmp = out + '.tmp'
    with gzip.open(tmp, 'wt', encoding='utf-8', compresslevel=9) as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<tv generator-info-name="iptv-epg">\n')
        chosen = []
        for m in mapping:
            src = pick_source(m['src'], progs)
            if not src:
                empty.append(m['name'])
                continue
            chosen.append((m, src))
            f.write(f'  <channel id={quoteattr(m["id"])}><display-name>{escape(m["name"])}</display-name></channel>\n')
        for m, src in chosen:
            used += 1
            for el in progs[src]:
                if (el.get('stop') or el.get('start'))[:14] < cutoff:
                    continue  # already over
                el.set('channel', m['id'])
                add_artwork(el)
                start, stop = el.get('start'), el.get('stop')
                if m.get('shift'):
                    el.set('start', shift_time(start, m['shift']))
                    if stop:
                        el.set('stop', shift_time(stop, m['shift']))
                el.tail = None
                f.write('  ' + re.sub(r'>\s*\n\s*<', '><', ET.tostring(el, encoding='unicode')).replace('\n', ' ') + '\n')
                el.set('start', start)
                if stop:
                    el.set('stop', stop)
                n_prog += 1
        f.write('</tv>\n')
    os.replace(tmp, out)
    print(f'guide channels with data: {used}/{len(mapping)}, programmes: {n_prog}')
    print(f'no data today ({len(empty)}): ' + '; '.join(empty[:60]) + (' ...' if len(empty) > 60 else ''))
    if used < len(mapping) * 0.5:
        sys.exit('fewer than half the channels have data; refusing to publish')


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2:])
