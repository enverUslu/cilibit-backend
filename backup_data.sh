#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/enver/cilibit"
BACKUP_DIR="$ROOT/backups"
STAMP="$(date +%Y%m%dT%H%M)"
ARCHIVE="$BACKUP_DIR/data-$STAMP.tar.gz"

mkdir -p "$BACKUP_DIR"
tar czf "$ARCHIVE" -C "$ROOT/backend/src" data static/uploads
sha256sum "$ARCHIVE" > "$ARCHIVE.sha256"
find "$BACKUP_DIR" -name 'data-*.tar.gz' -mtime +30 -delete
find "$BACKUP_DIR" -name 'data-*.tar.gz.sha256' -mtime +30 -delete

echo "$ARCHIVE"
