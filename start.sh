#!/usr/bin/env bash
# Start three local servers and register their MCP endpoints in Rakazo.
# If using Cloudflare, start both tunnels and update .env first.

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

PYTHON="$PWD/.venv/bin/python"

[[ -x "$PYTHON" ]] || {
    echo 'Create .venv and install requirements.txt first.' >&2
    exit 1
}

[[ -f .env ]] || {
    echo 'Copy .env.example to .env and configure it first.' >&2
    exit 1
}

# Validate environment settings and local ports.
# Parse dotenv with Python rather than sourcing it as shell code.
"$PYTHON" - <<'PY'
import os
import socket
from dotenv import load_dotenv

load_dotenv(".env")

required = [
    "RAKAZO_URL",
    "RAKAZO_ORIGIN",
    "RAKAZO_EMAIL",
    "RAKAZO_PASSWORD",
    "PAYMENTS_BOT_ID",
    "PAYMENTS_A2A_URL",
    "ASSISTANT_MCP_URL",
    "PAYMENTS_MCP_URL",
]

for prefix in ("ASSISTANT_MCP", "PAYMENTS_MCP", "PAYMENTS_A2A"):
    required.extend([prefix + "_HOST", prefix + "_PORT"])

missing = [key for key in required if not os.getenv(key)]

if missing:
    raise SystemExit(
        "Missing .env settings: " + ", ".join(missing)
    )

for prefix in ("ASSISTANT_MCP", "PAYMENTS_MCP", "PAYMENTS_A2A"):
    host = os.environ[prefix + "_HOST"]
    port = int(os.environ[prefix + "_PORT"])

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind((host, port))
    except OSError:
        raise SystemExit(
            f"{prefix}: cannot bind port {port}. "
            "Stop existing servers or check HOST/PORT."
        )

print("Environment and port checks passed.")
PY

pids=()

cleanup() {
    trap - EXIT INT TERM
    echo 'Stopping demo servers...'

    for pid in "${pids[@]}"; do
        kill -TERM "$pid" 2>/dev/null || true
    done

    for pid in "${pids[@]}"; do
        wait "$pid" 2>/dev/null || true
    done
}

trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

mkdir -p traces/demo

# Start Payments MCP.
"$PYTHON" -u mcp_servers/payments_server.py --http \
    >> traces/demo/payments-mcp.log 2>&1 &
pids+=("$!")

# Start Payments A2A gateway.
"$PYTHON" -u a2a/payments_a2a_server.py \
    >> traces/demo/payments-a2a.log 2>&1 &
pids+=("$!")

# Start Assistant MCP.
"$PYTHON" -u mcp_servers/assistant_server.py --http \
    >> traces/demo/assistant-mcp.log 2>&1 &
pids+=("$!")

echo 'Waiting for local servers (logs: traces/demo/)...'

"$PYTHON" - "${pids[@]}" <<'PY'
import os
import socket
import sys
import time
from dotenv import load_dotenv

load_dotenv(".env")

deadline = time.monotonic() + 30

while time.monotonic() < deadline:
    for pid in sys.argv[1:]:
        try:
            os.kill(int(pid), 0)
        except ProcessLookupError:
            raise SystemExit(
                "A server exited. Check traces/demo/*.log."
            )

    ready = True

    for prefix in ("ASSISTANT_MCP", "PAYMENTS_MCP", "PAYMENTS_A2A"):
        host = os.environ[prefix + "_HOST"]
        port = int(os.environ[prefix + "_PORT"])

        if host in ("0.0.0.0", "::"):
            host = "127.0.0.1"

        try:
            with socket.create_connection((host, port), timeout=0.3):
                pass
        except OSError:
            ready = False

    if ready:
        break

    time.sleep(0.2)
else:
    raise SystemExit(
        "Server startup timed out. Check traces/demo/*.log."
    )

print("Local servers are listening.")
PY

# Cloudflare tunnels, if used, must already be running.
"$PYTHON" - <<'PY'
import os
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv(".env")

for key in ("ASSISTANT_MCP_URL", "PAYMENTS_MCP_URL"):
    url = os.environ[key]
    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise SystemExit(f"Invalid {key}: {url}")

    if not parsed.path.endswith("/mcp"):
        raise SystemExit(f"{key} must end with /mcp")

    if "trycloudflare.com" in parsed.hostname:
        print(f"{key}: Cloudflare endpoint configured.")
        print("Ensure the corresponding tunnel is still running.")
PY

echo 'Registering MCP endpoints in Rakazo...'
"$PYTHON" connect_mcp.py

# Watch user requests and automatically export conversation/tool snapshots.
rm -f traces/demo/trace-watcher.ready
"$PYTHON" -u watch_traces.py --ready-file traces/demo/trace-watcher.ready \
    >> traces/demo/trace-watcher.log 2>&1 &
watcher_pid=$!
pids+=("$watcher_pid")

for ((attempt=0; attempt<60; attempt++)); do
    if [[ -f traces/demo/trace-watcher.ready ]]; then
        break
    fi
    if ! kill -0 "$watcher_pid" 2>/dev/null; then
        echo 'Trace watcher failed. Check traces/demo/trace-watcher.log.' >&2
        exit 1
    fi
    sleep 0.5
done
if [[ ! -f traces/demo/trace-watcher.ready ]]; then
    echo 'Trace watcher startup timed out. Check traces/demo/trace-watcher.log.' >&2
    exit 1
fi

echo ''
echo 'Ready. Open the Assistant chat in Rakazo.'
echo 'Automatic JSON traces: traces/phase1/request-*.json'
echo 'Press Ctrl+C to stop local servers and the trace watcher.'
echo 'Logs: traces/demo/'
echo ''

# Keep running until interrupted or a server exits.
while true; do
    for pid in "${pids[@]}"; do
        if ! kill -0 "$pid" 2>/dev/null; then
            echo 'A server stopped. Check traces/demo/*.log.' >&2
            exit 1
        fi
    done
    sleep 1
done
