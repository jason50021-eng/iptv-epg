#!/usr/bin/env python3
"""Nightly "what broke" report.

Compares last night's published guide with tonight's, per US channel in the provider's list, and writes
report.md: channels that had listings before but are blank now, new channels nobody could match, and totals.

Usage: report.py PREV_GUIDE.xml.gz NEW_GUIDE.xml.gz PREV_CHANNELS.json NEW_CHANNELS.json report.md
"""
import collections, datetime, gzip, json, os, re, sys
import xml.etree.ElementTree as ET

SLOT = re.compile(r'^USA\s+[^:]{0,40}?(\d{1,3}|Night)\s*:')
STATES = set('AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA LO ME MD MA MI MN MS MO MT NE NV NH NJ NM '
             'NY NC ND OH OK OR PA PR RI SC SD TN TX UT VT VA WA WV WI WY'.split())


def is_us_name(n):
    m = re.match(r'^([A-Z]{2})(?:-[A-Z]{2})? ?\|', n)
    return n.startswith('USA') or bool(m and m.group(1) in STATES)


def us_channels(path):
    if not path or not os.path.exists(path):
        return []
    chans = json.load(open(path, encoding='utf-8'))['channels']
    bygroup = collections.defaultdict(list)
    for c in chans:
        bygroup[c['group']].append(c)
    uscats = {g for g, v in bygroup.items() if sum(is_us_name(c['name']) for c in v) / len(v) >= 0.6}
    out = [c for c in chans if is_us_name(c['name']) or (c['group'] in uscats and not re.match(r'^(LA:|SUR|Latin)', c['name']))]
    return [c for c in out if not (SLOT.search(c['name']) and 'OCHO' not in c['name'].upper())]


def coverage(guide_path):
    """ids and display names that have at least one programme."""
    if not guide_path or not os.path.exists(guide_path) or os.path.getsize(guide_path) == 0:
        return None
    root = ET.parse(gzip.open(guide_path)).getroot()
    have = collections.Counter(p.get('channel') for p in root.iter('programme'))
    all_ids = {c.get('id') for c in root.findall('channel')}
    ids = {i for i in all_ids if have.get(i)}
    names = {(c.findtext('display-name') or '').strip() for c in root.findall('channel') if have.get(c.get('id'))}
    return ids, names, all_ids


def covered(c, cov):
    """Same order TiviMate uses: the channel's guide ID if the guide has it, otherwise its name."""
    ids, names, all_ids = cov
    if c.get('epg_id') and c['epg_id'] in all_ids:
        return c['epg_id'] in ids
    return c['name'] in names


def main(prev_guide, new_guide, prev_channels, new_channels, out):
    now_ch = us_channels(new_channels)
    before_names = {c['name'] for c in us_channels(prev_channels)}
    new_cov, old_cov = coverage(new_guide), coverage(prev_guide)
    lines = [f"# Guide report, {datetime.datetime.now(datetime.timezone.utc):%Y-%m-%d %H:%M} UTC", '']
    if new_cov is None:
        lines.append('Tonight\'s guide could not be read.')
    else:
        ok_now = [c for c in now_ch if covered(c, new_cov)]
        lines.append(f'US channels (not counting game channels): {len(now_ch)}. With listings tonight: {len(ok_now)}.')
        lost = []
        if old_cov is not None:
            lost = sorted({c['name'] for c in now_ch if covered(c, old_cov) and not covered(c, new_cov)})
            gained = sum(1 for c in now_ch if not covered(c, old_cov) and covered(c, new_cov))
            lines.append(f'Since last night: {len(lost)} lost their listings, {gained} gained listings.')
        newly = sorted({c['name'] for c in now_ch if c['name'] not in before_names and not covered(c, new_cov)}) if before_names else []
        lines += ['', f'## Lost listings since last night ({len(lost)})', '']
        lines += [f'- {n}' for n in lost[:150]] or ['- none']
        lines += ['', f'## New channels with no listings ({len(newly)})', '']
        lines += [f'- {n}' for n in newly[:150]] or ['- none']
    open(out, 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
    print('\n'.join(lines[:4]))


if __name__ == '__main__':
    main(*sys.argv[1:6])
