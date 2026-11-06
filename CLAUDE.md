# IPTV guide: notes for Claude

Jason McGuire's custom TV guide (XMLTV) for the US channels on his xtremehd IPTV playlist, used in TiviMate
on Google TV (onn) boxes. Built nightly by GitHub Actions in this repo and published to the `guide` branch.

TiviMate guide URL: https://raw.githubusercontent.com/jason50021-eng/iptv-epg/guide/guide.xml.gz

## Talking to Jason
- He is not a developer. Plain language, short, direct. Tell him what changed and what (if anything) he does.
- Never use em dashes in anything you write to him.
- His routine action is "Update EPG" in TiviMate. Avoid asking him to touch GitHub unless unavoidable.
- Do not print or echo the provider login. It lives only in repository secrets.

## How it works
- `channels.py` reads the provider's live channel list (groups, names, numbers, guide IDs; no stream links)
  into `channels.json`. Needs secrets IPTV_SERVER, IPTV_USER, IPTV_PASS.
- `matching/match.py` matches every US channel to free listing sources from iptv-org/epg site channel lists
  (call signs for locals, names/aliases for cable). `matching/gen.py` writes `mapping.json`,
  `sources/{tvpassport,ontvtonight,other}.channels.xml`, `manual-fixes.txt`, `no-guide.txt`.
- The grab jobs run iptv-org/epg's grabber on each sources file (starting yesterday, Central time, 4 days).
- `build.py` turns the raw grabs into guide.xml.gz using mapping.json: picks the source that covers the
  furthest ahead, shifts West feeds +3h when only East listings exist, copies `<image>` to `<icon>` for
  artwork, drops shows that already ended, refuses to publish if under half the channels have data.
- `events.py` adds listings for game slot channels (NFL Sunday 705-717, NBA 01, ESPN+ 016, NHL, soccer,
  PPV...) from the provider's current channel names. Runs hourly (games.yml) and in the nightly build.
- `report.py` writes `report.md`: channels that lost listings since last night, new channels with none.
- `publish.sh` force-pushes guide.xml.gz as the only file on the `guide` branch.

## Workflows (.github/workflows)
- guide.yml "Build TV guide": daily 08:23 UTC (2:23 AM Central). Jobs: match -> grab x3 -> publish.
  The match job keeps the previous mapping if matching fails or loses >10% of entries.
- games.yml "Update game listings": hourly, plus every 20 min Sundays 16:00-23:00 UTC.
- channels.yml "Save channel list": daily 07:41 UTC (also done inside the match job).

## TiviMate facts (verified Nov 5, 2026)
- In TiviMate, Jason's playlist uses ONLY this guide (the provider's own EPG source is unchecked).
- Matching: by the channel's provider guide ID if that ID exists in the guide, otherwise by exact name.
- Shared IDs: the provider gives some stations another station's ID (KYTV had WWLP's). Those IDs are not
  published (`matching/shared-ids.txt` = ALL), so those channels match by name. Confirmed working.
- Channel numbers in TiviMate = position within the group by provider order.

## Sources
- Work from GitHub: tvpassport.com (first choice, has descriptions/images), ontvtonight.com, epgshare01.online
  (whole-country files US1, US_LOCALS2, US_SPORTS1, FANDUEL1, PLEX1, DISTROTV1; grabbed one file per run because
  its grabber caches a single file), directv.com, tvinsider.com, tvguide.com, i.mjh.nz (Pluto/Samsung/Roku/Plex/PBS),
  plex.tv, pluto.tv, xumo.tv, distro.tv.
- Do NOT use from GitHub: tvtv.us and streamingtvguides.com return nothing.
- ontvtonight lists each market in local time but its grabber reads times as Eastern (Pacific stations 3h early).
  build.py calibrate_lineups() compares ontvtonight against tvpassport per market lineup and shifts it; it needs
  sources/index.json (written by gen.py). The shift per market is printed in status.txt.
- Samsung TV Plus (i.mjh.nz) only publishes a few hours ahead, and some sources skip a day. build.py picks, per
  channel, the source covering the most hours from 3h ago to 3 days ahead (earlier sources win when within 15%).

## Fixing a channel
1. Find why it is blank: is it in `no-guide.txt` (no match) or matched but empty (check `status.txt`)?
2. Renamed network (e.g. EPIX -> MGM+): add to ALIAS in `matching/match.py`. Provider names that no source
   uses (e.g. "Detroit SportsNet" = "FanDuel Sports Network Detroit"): add to MANUAL in `matching/match.py`. Local station: check its call
   sign exists in a source (`calls_idx`). Provider-specific oddity: OVERRIDE_CALLS or norm() rules.
3. Test locally before pushing:
   - `git clone --depth 1 --filter=blob:none --sparse https://github.com/iptv-org/epg.git` then
     `git sparse-checkout set sites`
   - `curl -o channels.csv https://raw.githubusercontent.com/iptv-org/database/master/data/channels.csv`
   - `EPG_SITES=epg/sites IPTV_ORG_DB=channels.csv CHANNELS=channels.json MATCH_WORK=/tmp/w MATCH_OUT=/tmp/o python3 matching/match.py && ... python3 matching/gen.py`
   - Compare /tmp/o/mapping.json with the committed one: entry count should not drop.
4. Commit, push to main, run `gh workflow run guide.yml`, wait, then verify the published guide
   (channels with data should not drop vs the previous guide; check the channels you fixed have shows).

## Safety and rollback
- Backup branches: `backup-before-improvements` (code as of Nov 5 evening, known good) and `backup-guide`
  (a known-good guide.xml.gz). To restore the guide instantly: push backup-guide's commit to `guide`.
- To undo a bad code change: `git revert` the commit on main and rerun the build.
- Never weaken the publish guard in build.py or the 10% guard in the match job.
- Things that are expected to have no guide: Starzplay/ViX/TUDN/Conmebol numbered slots, Music Choice video,
  small public-access channels. Don't spend time on these.

## If the provider's server address or login changes
Jason updates the repository secrets (Settings > Secrets and variables > Actions): IPTV_SERVER, IPTV_USER,
IPTV_PASS. The guide URL in TiviMate does not change.
