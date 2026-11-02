#!/bin/sh
# Daily pg_dump (format custom, -Fc) of the mailflow database.
# - verifies the dump with `pg_restore --list` before keeping it;
# - appends one timestamped OK/ECHEC line to backups/backup.log;
# - exits non-zero on any failure (the cron mail / watchdog can see it);
# - rotation: keeps the last 7 AUTOMATIC dumps only. Automatic dumps are
#   mailflow-auto-*.dump, plus the legacy name mailflow-AAAAMMJJ-0330.dump
#   written by the previous version of this script. Manual dumps (pre-update,
#   failback, any other mailflow-*.dump) are never counted nor removed.
set -eu
umask 077  # dumps contain mail data: owner-only

D="$HOME/mailflow/backups"
LOG="$D/backup.log"
CT=mailflow-postgres
KEEP=7
TS=$(date +%Y%m%d-%H%M)
OUT="$D/mailflow-auto-$TS.dump"
TMP="$OUT.tmp"

mkdir -p "$D"

# Writes to the log file only (cron also appends stdout/stderr to the same file).
log() {
  printf '%s %s\n' "$(date -Iseconds)" "$*" >> "$LOG"
  if [ -t 2 ]; then printf '%s\n' "$*" >&2; fi
}

fail() {
  log "ECHEC $*"
  rm -f "$TMP"
  exit 1
}

docker exec "$CT" sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$TMP" \
  || fail "pg_dump a echoue ($OUT)"

SIZE=$(wc -c < "$TMP")
[ "$SIZE" -gt 0 ] || fail "dump vide ($OUT)"

# Use the matching Postgres tools through stdin: no host dependency,
# docker cp, or temporary file to clean up inside the container.
LIST=$(docker exec -i "$CT" pg_restore --list < "$TMP" 2>&1) \
  || fail "pg_restore --list refuse le dump ($OUT)"

TABLES=$(printf '%s\n' "$LIST" | grep -c 'TABLE DATA' || true)
[ "$TABLES" -gt 0 ] || fail "dump sans donnees de table dans le sommaire ($OUT)"

mv "$TMP" "$OUT" || fail "renommage impossible ($TMP)"

# Rotation: automatic dumps only (newest first, drop everything past $KEEP).
ls -1t "$D"/mailflow-auto-*.dump "$D"/mailflow-????????-0330.dump 2>/dev/null \
  | tail -n +"$((KEEP + 1))" | xargs -r rm -f

log "OK $(basename "$OUT") ($SIZE octets, $TABLES tables, verifie par pg_restore --list)"
