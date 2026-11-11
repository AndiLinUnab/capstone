#!/bin/bash
# Respaldo de InfluxDB (bucket capstone). El token no sale del contenedor.
set -e
cd "$(dirname "$0")/.."
DEST=~/backups/influx-$(date -u +%Y%m%d-%H%M)
mkdir -p "$DEST"
docker compose exec -T influxdb sh -c 'rm -rf /tmp/bk && influx backup /tmp/bk -t "$DOCKER_INFLUXDB_INIT_ADMIN_TOKEN" >/dev/null'
docker cp influxdb:/tmp/bk/. "$DEST"/
docker compose exec -T influxdb rm -rf /tmp/bk
find ~/backups -maxdepth 1 -name 'influx-*' -mtime +10 -exec rm -rf {} +
echo "OK $DEST $(du -sh "$DEST" | cut -f1)"
