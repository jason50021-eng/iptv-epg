#!/usr/bin/env bash
# Force-push guide.xml.gz as the only file on the "guide" branch (keeps the repo small).
set -euo pipefail
rm -rf out && mkdir out && cp guide.xml.gz out/ && cd out
git init -q -b guide
git add guide.xml.gz
git -c user.name=guide-bot -c user.email=guide-bot@users.noreply.github.com commit -q -m "guide $(date -u '+%F %H:%M')"
git push -q -f "https://x-access-token:${GITHUB_TOKEN}@github.com/${GITHUB_REPOSITORY}.git" guide
