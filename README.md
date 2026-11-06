# IPTV TV guide

Builds a daily XMLTV guide (`guide.xml.gz`) for the US channels in my IPTV playlist, named to match the
provider's channel names and guide IDs so TiviMate links them automatically.

**Guide URL for TiviMate:** `https://raw.githubusercontent.com/jason50021-eng/iptv-epg/guide/guide.xml.gz`

- Runs every day at about 2:23 AM Central (Actions tab, "Build TV guide"). Use "Run workflow" to refresh by hand.
- Listings come from free sources via [iptv-org/epg](https://github.com/iptv-org/epg): tvpassport.com (with
  descriptions), tvtv.us as a backup, plus Pluto, Samsung TV Plus, Plex and a few others.
- **Game listings** (Actions tab, "Update game listings"): every hour, and every 20 minutes on Sunday
  afternoons, `events.py` reads the provider's current channel names (NFL Sunday 7xx, NBA, NHL, ESPN+, soccer,
  PPV...) and turns each one into a guide block at the right time. It needs three repository secrets
  (Settings > Secrets and variables > Actions): `IPTV_SERVER` (e.g. `http://xtremehd.cc:80`), `IPTV_USER`,
  `IPTV_PASS`. Secrets are encrypted and never shown in this public repo or its logs. Without them the
  rest of the guide still works.
- `status.txt` shows the last run and which channels got no data that day.
- `manual-fixes.txt`: channels that need a one-time guide pick in TiviMate.
- `no-guide.txt`: channels no free source carries.
- `mapping.json`: provider channel to guide source mapping. `sources/*.channels.xml`: what gets downloaded.

This repo holds no login details (the game listings read them from encrypted secrets). The playlist itself never leaves TiviMate.
