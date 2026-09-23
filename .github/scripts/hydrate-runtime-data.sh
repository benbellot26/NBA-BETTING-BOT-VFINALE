#!/usr/bin/env bash
set -euo pipefail
git fetch origin runtime-data || true
if git show-ref --verify --quiet refs/remotes/origin/runtime-data; then
  rm -rf runtime
  git archive origin/runtime-data runtime 2>/dev/null | tar -x || true
fi
