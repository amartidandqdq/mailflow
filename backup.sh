#!/bin/sh
# Daily pg_dump of the mailflow database, keeps the last 7 dumps.
set -eu
umask 077  # dumps contain mail data: owner-only
D="$HOME/mailflow/backups"
mkdir -p "$D"
docker exec mailflow-postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$D/mailflow-$(date +%Y%m%d-%H%M).dump.tmp"
mv "$D/mailflow-$(date +%Y%m%d-%H%M).dump.tmp" "$D/mailflow-$(date +%Y%m%d-%H%M).dump"
ls -1t "$D"/mailflow-*.dump | tail -n +8 | xargs -r rm -f
