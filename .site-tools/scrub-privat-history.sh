#!/bin/zsh
# scrub-privat-history.sh
#
# Fjerner Privat/Sardinfabrikken.html (som ved en feil ble lastet opp i
# ren tekst til GitHub tidligere) fra HELE git-historikken, og publiserer
# den ryddede historikken til GitHub.
#
# KJØR DENNE SELV I DIN EGEN TERMINAL — ikke via automatisering.
# Dette er en tung og irreversibel operasjon (omskriver 200 commits i et
# ca. 884 MB stort repo) og kan ta flere minutter. Ikke lukk Terminal
# eller slå av Mac'en mens den kjører.
#
# FØR DU KJØRER:
#  1. Lukk eventuelle andre programmer som rører ved GitHub-mappen
#     (f.eks. sørg for at auto-publish-overvåkeren ikke kjører akkurat nå).
#  2. Sørg for at du har internettforbindelse (siste steg trenger nett).

set -euo pipefail

REPO="/Users/einar/Documents/GitHub/gamleulv.github.io"
BACKUP="/Users/einar/Documents/gamleulv-backup-$(date +%Y%m%d-%H%M%S).bundle"

cd "$REPO"

echo "== 1/6: Lager sikkerhetskopi av HELE repoet (alle branches/tags) til:"
echo "        $BACKUP"
git bundle create "$BACKUP" --all
echo "        Ferdig. Behold denne filen til du er sikker på at alt gikk bra."
echo

echo "== 2/6: Sjekker at treet er rent før vi starter …"
if [ -n "$(git status --porcelain)" ]; then
  echo "FEIL: Du har uncommitted endringer. Commit eller stash dem først, og prøv igjen."
  exit 1
fi
echo "        OK."
echo

echo "== 3/6: Skriver om historikken (dette tar tid – vær tålmodig) …"
FILTER_BRANCH_SQUELCH_WARNING=1 git filter-branch --force \
  --index-filter "git rm --cached --ignore-unmatch Privat/Sardinfabrikken.html" \
  --prune-empty --tag-name-filter cat -- --all
echo "        Ferdig med omskriving."
echo

echo "== 4/6: Rydder opp gamle referanser og komprimerer repoet …"
rm -rf .git/refs/original/
git reflog expire --expire=now --all
git gc --prune=now --aggressive
echo "        Ferdig."
echo

echo "== 5/6: Verifiserer at filen er borte fra all historikk …"
if git log --all --oneline -- Privat/Sardinfabrikken.html | grep -q .; then
  echo "ADVARSEL: Filen dukker fortsatt opp i historikken. IKKE push videre –"
  echo "gjenopprett fra sikkerhetskopien ($BACKUP) og gi beskjed."
  exit 1
fi
echo "        Bekreftet: Privat/Sardinfabrikken.html finnes ikke lenger i noen commit."
echo

echo "== 6/6: Publiserer den ryddede historikken til GitHub (force-push) …"
git push origin --force --all
git push origin --force --tags
echo
echo "FERDIG. Historikken er skrubbet og publisert."
echo "Sikkerhetskopien ligger fortsatt her om du trenger den: $BACKUP"
echo
echo "VIKTIG: Fordi filen har ligget offentlig på GitHub en periode, bør du"
echo "regne innholdet i den filen som eksponert (GitHub kan ha cachet/indeksert"
echo "det, og andre kan ha lastet det ned før du fjernet det). Skrubbingen"
echo "hindrer nye visninger, men endrer ikke det som historisk kan ha blitt sett."
