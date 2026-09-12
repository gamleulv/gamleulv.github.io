#!/bin/bash
# auto-publish.sh — regenerate and publish gamleulv.github.io
#
# All the real work (repairing old corruption, generating navigation pages,
# building the search index, encrypting the Privat folder, etc.) lives in
# .site-tools/generate_site.py. This script just: run the generator, then
# commit and push if anything changed.
#
# Triggered by auto-publish-watcher.sh whenever a file changes in the repo
# or in the external Privat-kilde folder.

set -euo pipefail

REPO="/Users/einar/Documents/GitHub/gamleulv.github.io"
LOG_FILE="$REPO/.site-tools/publish.log"
LOCK_DIR="$REPO/.site-tools/.publish.lock"
PAUSE_FILE="$REPO/.site-tools/.paused"

cd "$REPO"

# Manual maintenance pause switch: if this file exists, do nothing at all.
if [ -f "$PAUSE_FILE" ]; then
  exit 0
fi

# Simple atomic lock so overlapping fswatch triggers can't race each other.
# A stale lock (crashed run) older than 10 minutes is cleared automatically.
if [ -d "$LOCK_DIR" ]; then
  if [ -n "$(find "$LOCK_DIR" -maxdepth 0 -mmin +10 2>/dev/null)" ]; then
    rm -rf "$LOCK_DIR"
  else
    exit 0
  fi
fi
mkdir "$LOCK_DIR"
trap 'rm -rf "$LOCK_DIR"' EXIT

{
  echo "== $(date '+%Y-%m-%d %H:%M:%S') =="

  # Regenerate the whole site (repairs content, rebuilds nav/search, encrypts Privat)
  python3 .site-tools/generate_site.py "$REPO"

  # Safety net: iCloud has been observed resurrecting old plaintext copies of
  # files that were deleted from Privat/ (from its own cloud cache). Never
  # commit or push if ANYTHING in Privat/ isn't the expected encrypted blob -
  # refuse and alert instead of silently re-leaking private content.
  for f in "$REPO"/Privat/*.html; do
    [ -e "$f" ] || continue
    [ "$(basename "$f")" = "index.html" ] && continue
    if ! grep -q '"ciphertext"' "$f"; then
      echo "STOPPET: $f i Privat/ er IKKE kryptert (mangler 'ciphertext'-felt)."
      echo "Ingen commit/push kjørt. Sjekk om iCloud har gjenopprettet en gammel fil."
      exit 1
    fi
  done

  # Only commit/push if the generator actually changed something
  if [ -n "$(git status --porcelain)" ]; then
    git add -A
    git commit -m "Auto-publish: $(date '+%Y-%m-%d %H:%M')"
    git push origin main
    echo "Publisert."
  else
    echo "Ingen endringer å publisere."
  fi
} >> "$LOG_FILE" 2>&1
