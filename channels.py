#!/usr/bin/env python3
"""Save the provider's live channel list (groups, names, numbers, guide IDs) to channels.json.

No stream links or login details are written. Used to build the channel guide page and to
re-check channel matching when the provider renames or adds channels.
"""
import json, os, sys, urllib.parse, urllib.request


def api(action):
    server = os.environ['IPTV_SERVER'].rstrip('/')
    if not server.startswith('http'):
        server = 'http://' + server
    q = urllib.parse.urlencode({'username': os.environ['IPTV_USER'], 'password': os.environ['IPTV_PASS'],
                                'action': action})
    req = urllib.request.Request(f'{server}/player_api.php?{q}', headers={'User-Agent': 'TiviMate/5.1.6'})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.load(r)


def main(out):
    cats = api('get_live_categories')
    streams = api('get_live_streams')
    order = {str(c['category_id']): i for i, c in enumerate(cats)}
    data = {
        'groups': [{'id': str(c['category_id']), 'name': c['category_name']} for c in cats],
        'channels': [{'num': int(s.get('num') or 0), 'name': (s.get('name') or '').strip(),
                      'group': str(s.get('category_id')), 'epg_id': s.get('epg_channel_id') or None,
                      'stream_id': s.get('stream_id')} for s in streams],
    }
    data['channels'].sort(key=lambda c: (order.get(c['group'], 9999), c['num']))
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=0)
    print(f"{len(data['groups'])} groups, {len(data['channels'])} channels")


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'channels.json')
