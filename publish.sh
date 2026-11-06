#!/usr/bin/env bash
# Force-push guide.xml.gz as the only file on the "guide" branch (keeps the repo small).
set -euo pipefail
rm -rf out && mkdir out && cp guide.xml.gz out/ && cd out
git init -q -b guide
git add guide.xml.gz
git -c user.name=guide-bot -c user.email=guide-bot@users.noreply.github.com commit -q -m "guide $(date -u '+%F %H:%M')"
REMOTE="https://x-access-token:${GITHUB_TOKEN}@github.com/${GITHUB_REPOSITORY}.git"
if [ -n "${LEASE:-}" ]; then
  # hourly game update: only replace the guide if nobody published a newer one since we read it
  git push -q --force-with-lease="guide:${LEASE}" "$REMOTE" guide \
    || echo "guide changed while updating game listings; skipped (next hourly run will add them)"
else
  git push -q -f "$REMOTE" guide
fi
