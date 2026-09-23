#!/usr/bin/env bash
set -euo pipefail
if [ ! -d runtime ]; then
  echo "No runtime directory; nothing to persist."
  exit 0
fi
rm -rf /tmp/pulsar-runtime
cp -a runtime /tmp/pulsar-runtime
git fetch origin runtime-data || true
if git show-ref --verify --quiet refs/remotes/origin/runtime-data; then
  git checkout -B runtime-data origin/runtime-data
else
  git checkout --orphan runtime-data
fi
# runtime-data is intentionally data-only. Remove any legacy source-tree files.
git rm -rf . >/dev/null 2>&1 || true
rm -rf runtime
cp -a /tmp/pulsar-runtime runtime
git config user.name "pulsar-nba-bot"
git config user.email "actions@users.noreply.github.com"
git add -f runtime
if git diff --cached --quiet; then
  echo "No runtime changes."
  exit 0
fi
git commit -m "runtime: persist NBA research state [skip ci]"
git push origin runtime-data
