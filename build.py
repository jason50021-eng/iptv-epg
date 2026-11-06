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


def coverage_end(els):
    return max((e.get('stop') or e.get('start'))[:14] for e in els)


def pick_source(keys, progs):
    """Prefer sources in listed order, but skip one that stops far earlier than another
    (e.g. Samsung TV Plus only publishes a few hours ahead; Plex has three days)."""
    have = [k for k in keys if progs.get(k)]
    if not have:
        return None
    ends = {k: datetime.datetime.strptime(coverage_end(progs[k]), FMT) for k in have}
    best = max(ends.values())
    return next(k for k in have if ends[k] >= best - datetime.timedelta(hours=12))


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


def main(out, raws):
    mapping = json.load(open(os.path.join(HERE, 'mapping.json'), encoding='utf-8'))
    progs = load_programmes(raws)
    used, empty, n_prog = 0, [], 0
    cutoff = (datetime.datetime.utcnow() - datetime.timedelta(hours=3)).strftime(FMT)
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
