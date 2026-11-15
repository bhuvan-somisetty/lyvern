#!/usr/bin/env bash
# Export the tracked files of HEAD into a plain folder (no .git, .venv or node_modules).
# Usage: scripts/export_snapshot.sh "/c/Users/<you>/OneDrive/Desktop/PROJECTS/AI PR Review Bot"
# The target is a read-only-style snapshot for browsing; the git repository stays the source of truth.
set -euo pipefail
target="${1:?usage: export_snapshot.sh <target-folder>}"
mkdir -p "$target"
git archive --format=tar HEAD | tar -xf - -C "$target"
printf 'Snapshot of commit %s exported on %s\n' "$(git rev-parse --short HEAD)" "$(date '+%Y-%m-%d %H:%M %Z')" > "$target/SNAPSHOT_INFO.txt"
echo "exported $(git rev-parse --short HEAD) to $target"
