#!/bin/bash
# backup.sh — kopia zapasowa bazy danych SQLite
# Uruchom jako cron: 0 3 * * * /ścieżka/do/backup.sh

BACKUP_DIR="/var/backups/rzeczy"
DB_PATH="/var/www/rzeczy/backend/rzeczy.db"
DATE=$(date +%Y-%m-%d_%H-%M)
MAX_BACKUPS=30  # Przechowuj ostatnie 30 kopii

mkdir -p "$BACKUP_DIR"

# Kopia z użyciem SQLite .dump (bezpieczna podczas działania aplikacji)
sqlite3 "$DB_PATH" ".backup '$BACKUP_DIR/rzeczy_$DATE.db'"

# Usuń stare kopie (zostaw MAX_BACKUPS)
ls -t "$BACKUP_DIR"/rzeczy_*.db | tail -n +$((MAX_BACKUPS + 1)) | xargs -r rm

echo "[$(date)] Backup: $BACKUP_DIR/rzeczy_$DATE.db"
