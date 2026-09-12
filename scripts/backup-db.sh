#!/usr/bin/env sh
# Dump the production database to ./backups and delete dumps older than KEEP_DAYS.
#
#   ./scripts/backup-db.sh
#
# Nightly at 03:15, from the repository directory (crontab -e):
#   15 3 * * * cd /srv/alhidaya && ./scripts/backup-db.sh >> backups/backup.log 2>&1
#
# Restore into an empty database:
#   gunzip -c backups/alhidaya-YYYYmmdd-HHMMSS.sql.gz \
#     | docker compose -f docker-compose.yml exec -T db psql -U alhidaya -d alhidaya
set -eu

cd "$(dirname "$0")/.."
KEEP_DAYS="${KEEP_DAYS:-14}"
OUT_DIR="${OUT_DIR:-backups}"
COMPOSE="docker compose -f docker-compose.yml"

mkdir -p "$OUT_DIR"
DB_USER="$(grep -E '^POSTGRES_USER=' .env | cut -d= -f2- || true)"
DB_NAME="$(grep -E '^POSTGRES_DB=' .env | cut -d= -f2- || true)"
: "${DB_USER:=alhidaya}"
: "${DB_NAME:=alhidaya}"

STAMP="$(date -u +%Y%m%d-%H%M%S)"
TMP="$OUT_DIR/.$DB_NAME-$STAMP.sql.gz.partial"
FINAL="$OUT_DIR/$DB_NAME-$STAMP.sql.gz"

# Write to a .partial file first, so an interrupted run never leaves a truncated dump that looks good.
$COMPOSE exec -T db pg_dump -U "$DB_USER" -d "$DB_NAME" --clean --if-exists | gzip -9 > "$TMP"
mv "$TMP" "$FINAL"
echo "$(date -u +%FT%TZ) wrote $FINAL ($(du -h "$FINAL" | cut -f1))"

find "$OUT_DIR" -name "$DB_NAME-*.sql.gz" -mtime "+$KEEP_DAYS" -print -delete
