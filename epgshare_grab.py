#!/usr/bin/env python3
"""Fast epgshare01 grab: download each country file once and keep only the channels we use.

Reads sources/epgshare-<TAG>.channels.xml (written by matching/gen.py) and writes raw-epgshare-<TAG>.xml with
programmes renamed to our source keys (S0001...), the same format the iptv-org grabber produces.
Usage: epgshare_grab.py OUTPUT_DIR
"""
import glob, gzip, html, io, os, sys, urllib.request
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
out_dir = sys.argv[1] if len(sys.argv) > 1 else '.'

for path in sorted(glob.glob(os.path.join(HERE, 'sources', 'epgshare-*.channels.xml'))):
    tag = os.path.basename(path)[len('epgshare-'):-len('.channels.xml')]
    want = {}
    for ch in ET.parse(path).getroot():
        want[ch.get('site_id').split('#', 1)[1]] = ch.get('xmltv_id')
    url = os.environ.get('EPGSHARE_BASE', 'https://epgshare01.online/epgshare01') + f'/epg_ripper_{tag}.xml.gz'
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'iptv-epg/1.0'})
        data = urllib.request.urlopen(req, timeout=300).read()
    except Exception as e:
        print(f'{tag}: download failed ({type(e).__name__}: {e})')
        continue
    kept, seen = 0, set()
    with open(os.path.join(out_dir, f'raw-epgshare-{tag}.xml'), 'w', encoding='utf-8') as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<tv>\n')
        for _, el in ET.iterparse(gzip.GzipFile(fileobj=io.BytesIO(data)), events=('end',)):
            if el.tag == 'programme':
                key = want.get(el.get('channel'))
                if key:
                    el.set('channel', key)
                    el.tail = None
                    f.write(ET.tostring(el, encoding='unicode').replace('\n', ' ') + '\n')
                    kept += 1
                    seen.add(key)
                el.clear()
            elif el.tag == 'channel':
                el.clear()
        f.write('</tv>\n')
    print(f'{tag}: {len(data) // 1024} KB, {len(seen)}/{len(want)} channels found, {kept} programmes')
