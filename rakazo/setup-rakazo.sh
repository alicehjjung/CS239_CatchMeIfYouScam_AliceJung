#!/usr/bin/env bash
set -euo pipefail
SCRIPT_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
readonly RAKAZO_REVISION=932534d7785f0c51b6a0aed54d0096ea8b36eb11
readonly INSTALLER_SHA256=6e9c4472d116531b950081d618168abbd1d3a2b85317fe3528eb715ee9abf560
readonly RUNTIME_DIR="$SCRIPT_ROOT/.rakazo-runtime"
export COMPOSE_PROJECT_NAME=cs239-tutorial-rakazo
export RAKAZO_API_PORT=23100
export RAKAZO_DOWNLOAD_BASE="https://raw.githubusercontent.com/elie222/rakazo/$RAKAZO_REVISION/infra/compose"
for task_command in docker curl openssl python3; do
  command -v "$task_command" >/dev/null || { echo "Install $task_command first (Docker Desktop includes Docker Compose)." >&2; exit 1; }
done
docker compose version >/dev/null
docker info >/dev/null 2>&1 || { echo 'Start Docker Desktop / Docker Engine first.' >&2; exit 1; }
if [[ "${1:-start}" == stop ]]; then
  [[ -f "$RUNTIME_DIR/docker-compose.images.yml" ]] || { echo 'No tutorial stack has been installed.'; exit 0; }
  cd "$RUNTIME_DIR"
  docker compose --env-file .env -f docker-compose.images.yml down
  exit 0
fi
[[ "${1:-start}" == start ]] || { echo 'Usage: bash setup-rakazo.sh [start|stop]' >&2; exit 2; }
if python3 -c 'import socket; s=socket.socket(); result=s.connect_ex(("127.0.0.1",5173)); s.close(); raise SystemExit(0 if result == 0 else 1)'; then
  if [[ ! -f "$RUNTIME_DIR/docker-compose.images.yml" || ! -f "$RUNTIME_DIR/.env" ]] ||
     ! (cd "$RUNTIME_DIR" && docker compose --env-file .env -f docker-compose.images.yml ps --status running --services) | grep -qx web; then
    echo 'Port 5173 is already in use. Connect your existing app in the slides, or free that port before installing this tutorial stack.' >&2
    exit 1
  fi
fi
umask 077
mkdir -p "$RUNTIME_DIR"
cd "$RUNTIME_DIR"
# Verify the pinned upstream bootstrap before running it. No local app source is copied.
curl -fsSL --proto '=https' --proto-redir '=https' --connect-timeout 15 --max-time 120 \
  "$RAKAZO_DOWNLOAD_BASE/install-images.sh" -o install-images.sh.download
python3 - "$INSTALLER_SHA256" <<'PY'
import hashlib,sys
from pathlib import Path
path=Path('install-images.sh.download')
if hashlib.sha256(path.read_bytes()).hexdigest()!=sys.argv[1]:
    path.unlink()
    raise SystemExit('Upstream installer checksum mismatch; startup refused.')
path.replace('install-images.sh')
PY
bash install-images.sh --prepare-only --local
# Let both agent processes reach the tutorial MCP server on the student's host.
python3 - <<'PYHOST'
from pathlib import Path
import re
path=Path('docker-compose.images.yml')
source=path.read_text()
if 'host.docker.internal:host-gateway' not in source:
    for service in ('api','worker'):
        marker=rf'^  {service}:\n'
        if len(re.findall(marker,source,re.MULTILINE))!=1:
            raise SystemExit('Unexpected upstream Compose layout; startup refused.')
        source=re.sub(marker,lambda match: match.group(0)+'    extra_hosts:\n      - "host.docker.internal:host-gateway"\n',source,count=1,flags=re.MULTILINE)
    path.write_text(source)
PYHOST
bash install-images.sh --local
