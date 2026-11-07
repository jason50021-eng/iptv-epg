# Guide change log

Each change lists what it does, what we expected, and how to undo it.
Restore points are git branches; see "Safety and rollback" in CLAUDE.md.

## 2026-11-07: Game Channels Update
Restore point before this change: `restore-code-2026-11-07-0944` / `restore-guide-2026-11-07-0944`.

What changed (events.py, guide.yml):
- Game channels in more groups now get listings, not only names starting with "USA": NCAAF, NCAAB, NCAA women's
  basketball, NJCAA, FloSports, DAZN, Soccer Special Events, Pay Per View Events, PPV-MMA/Boxing/WWE/UFC, Lacrosse,
  Tennis, Golf, College Baseball, Softball, NBA G League, Rugby, Cycling, Handball, Motorsports, Canada Sportsnet+.
- New time formats understood: "@ 6 Nov 07:00 PM ET" and "(11.6 7:00 PM ET)".
- No more blank game channels: "Up next: X" before the start, X during it, "Ended: X" after it until the provider
  renames the channel, the event name all day when no time is given, "No event scheduled" for empty slots.
- Old-name protection: each game channel is also listed under its last 2 names, so a TiviMate channel list
  that is a couple of hours old still finds the listing.
- Regular channels (locals, cable, movies) are not touched.

Expected: about 1,060 game channels with listings (was about 560); regular channels identical; guide about 1% bigger.
TiviMate setting done the same day: playlist update every 2 hours plus on app start (was every 24 hours).

To undo: `git revert` this commit on main, then run "Update game listings" (or wait for the hourly run).
