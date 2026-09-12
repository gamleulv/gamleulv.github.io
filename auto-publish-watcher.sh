#!/bin/zsh
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

REPO="/Users/einar/Documents/GitHub/gamleulv.github.io"
PRIVAT_SOURCE="/Users/einar/Documents/Privat-kilde"
SCRIPT="$REPO/auto-publish.sh"

echo "Starter overvåking av $REPO og $PRIVAT_SOURCE"

# -r          : recursive (watch subfolders and sub-subfolders too)
# -o          : batch each burst of changes into a single event
# --latency 3 : wait 3s after the last change before firing, so a folder full
#               of dragged-in files triggers one publish, not dozens
# --exclude   : ignore the generator's OWN output and internals, so a publish
#               run doesn't immediately re-trigger itself in a loop
fswatch -r -o --latency 3 \
  --exclude '/\.git/' \
  --exclude '\.DS_Store$' \
  --exclude '/index\.html$' \
  --exclude '/search-index\.json$' \
  --exclude '/sitemap\.xml$' \
  --exclude '/rss\.xml$' \
  --exclude '\.nojekyll$' \
  --exclude 'publish\.log$' \
  --exclude '\.publish\.lock' \
  --exclude '__pycache__/' \
  "$REPO" "$PRIVAT_SOURCE" | while read -r _count; do
    echo "Endring oppdaget – publiserer..."
    "$SCRIPT"
done
