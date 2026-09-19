#!/bin/bash
set -euo pipefail

REPO="/Users/einar/Documents/GitHub/gamleulv.github.io"
TOOLS="$REPO/.site-tools"
LOG_FILE="$TOOLS/publish.log"
LOCK_DIR="$TOOLS/.publish.lock"
PAUSE_FILE="$TOOLS/.paused"

cd "$REPO"
[ -f "$PAUSE_FILE" ] && exit 0

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

  # Build only the public site. Privat is deliberately untouched.
  GAMLEULV_PUBLIC_ONLY=1 python3 "$TOOLS/generate_site.py" "$REPO"

  # A public publish must not change anything below Privat.
  if [ -n "$(git status --porcelain -- Privat)" ]; then
    echo "STOPPET: Det finnes endringer under Privat/. Ingen commit eller push ble utført."
    git status --short -- Privat
    exit 1
  fi

  # Never allow duplicate collision files from the earlier incident.
  if find "$REPO/Privat" -type f -name '* 2.html' -print -quit | grep -q .; then
    echo "STOPPET: Fant en fil under Privat/ som ender med ' 2.html'."
    exit 1
  fi

  # Stage tracked changes and newly added public files, but never Privat or logs.
  git add -A -- . \
    ':(exclude)Privat/**' \
    ':(exclude).site-tools/publish.log' \
    ':(exclude).site-tools/watcher.log' \
    ':(exclude).site-tools/.publish.lock/**' \
    ':(exclude).site-tools/.paused'

  # Abort on any deletion or rename. Adding/modifying files is allowed.
  if git diff --cached --name-status | grep -Eq '^(D|R)'; then
    echo "STOPPET: Publiseringen inneholder sletting eller omdøping:"
    git diff --cached --name-status | grep -E '^(D|R)'
    git reset
    exit 1
  fi

  # GitHub rejects ordinary Git objects above 100 MiB.
  too_large="$(git diff --cached --name-only --diff-filter=AM -z | \
    while IFS= read -r -d '' file; do
      [ -f "$file" ] || continue
      size=$(stat -f%z "$file" 2>/dev/null || stat -c%s "$file")
      [ "$size" -gt 104857600 ] && printf '%s (%s bytes)\n' "$file" "$size"
    done)"
  if [ -n "$too_large" ]; then
    echo "STOPPET: En eller flere filer er større enn 100 MiB:"
    printf '%s\n' "$too_large"
    git reset
    exit 1
  fi

  if git diff --cached --quiet; then
    echo "Ingen endringer å publisere."
    exit 0
  fi

  git commit -m "Auto-publish: $(date '+%Y-%m-%d %H:%M')"
  git push origin main
  echo "Publisert."
} >> "$LOG_FILE" 2>&1
