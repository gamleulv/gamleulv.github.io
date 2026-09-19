#!/bin/zsh
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
REPO="/Users/einar/GitHub/gamleulv.github.io"
SCRIPT="$REPO/auto-publish.sh"

echo "Starter offentlig overvåking av $REPO"

/opt/homebrew/bin/fswatch -r -o --latency 3 \
  --exclude '/\.git/' \
  --exclude '/\.site-tools/' \
  --exclude '/Privat/' \
  --exclude '/index\.html$' \
  --exclude '/search-index\.json$' \
  --exclude '/sitemap\.xml$' \
  --exclude '/rss\.xml$' \
  --exclude '\.nojekyll$' \
  --exclude '\.DS_Store$' \
  "$REPO" | while read -r _count; do
    echo "Offentlig endring oppdaget - publiserer..."
    "$SCRIPT"
done
