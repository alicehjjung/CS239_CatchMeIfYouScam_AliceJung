# Catch Me If You Scam

`Catch Me If You Scam` is a two-agent financial fraud prevention demo. A user-facing **Assistant Agent** analyzes potentially scam messages and requests payment verification from a bank-side **Payments Agent** through Agent-to-Agent (A2A) communication.

Both agents run in Rakazo and use Model Context Protocol (MCP) tools to access simulated messages and banking data. No real banking service is connected, and no real money is transferred.

## 1. Requirements

- Python 3.13+
- Docker with Compose
- Rakazo account and supported LLM provider
- `cloudflared` (for HTTPS MCP tunnels when required)

The Rakazo setup script also requires `curl`, `openssl`, and `python3`.

Initial installation requires internet access. Hosted LLM providers may incur API charges.

## 2. Installation

Run all commands from the repository root using a macOS/Linux shell.

Create a virtual environment and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Create the environment configuration file:

```bash
cp -n .env.example .env
```

Configure the following variables in `.env`:

| Variable | Description |
|---|---|
| `RAKAZO_URL` | Rakazo API URL, default `http://localhost:23100` |
| `RAKAZO_ORIGIN` | Rakazo web origin, default `http://127.0.0.1:5173` |
| `RAKAZO_EMAIL` | Rakazo account email |
| `RAKAZO_PASSWORD` | Rakazo account password |
| `PAYMENTS_BOT_ID` | ID of the Payments bot |
| `ASSISTANT_MCP_URL` | Assistant MCP endpoint |
| `PAYMENTS_MCP_URL` | Payments MCP endpoint |
| `PAYMENTS_A2A_URL` | Local Payments A2A gateway URL |

The default local service ports are:

| Service | Port |
|---|---|
| Assistant MCP | `8766` |
| Payments MCP | `8767` |
| Payments A2A gateway | `9999` |

Additional host, port, and logging settings are defined in `.env.example`.

## 3. Set Up Rakazo

Start Docker and run:

```bash
bash rakazo/setup-rakazo.sh
```

Open `http://127.0.0.1:5173`.

1. Create a local Rakazo account and update your credentials in `.env`.
2. Configure an LLM provider and select a model.
3. Create two bots named `Assistant` and `Payments`.
4. Copy the contents of `agents/assistant.md` and `agents/payments.md` into their respective bot instructions.

### Configure the Payments Bot ID

The Payments bot ID is specific to your Rakazo environment and must be retrieved after creating the bot.

Run:

```bash
.venv/bin/python - <<'PY'
import os
from dotenv import load_dotenv
from rakazo.rakazo import Rakazo

load_dotenv(".env")

with Rakazo(
    os.environ["RAKAZO_URL"],
    origin=os.environ["RAKAZO_ORIGIN"]
) as client:
    client.login(
        os.environ["RAKAZO_EMAIL"],
        os.environ["RAKAZO_PASSWORD"]
    )
    for bot in client.rpc("bots/list"):
        print(bot["name"], bot["id"])
PY
```

Copy the ID into `.env`:

```dotenv
PAYMENTS_BOT_ID=your_payments_bot_id
ASSISTANT_BOT_ID=your_assisant_bot_id
```

The A2A gateway uses this ID to route verification requests to the correct Payments bot.

## 4. Start Cloudflare Tunnels

If Rakazo requires HTTPS MCP endpoints, use Cloudflare tunnels to expose the local MCP servers.

Start the following commands in **two separate terminals**.

**Terminal 1: Assistant MCP tunnel**

```bash
cloudflared tunnel --url http://127.0.0.1:8766
```

**Terminal 2: Payments MCP tunnel**

```bash
cloudflared tunnel --url http://127.0.0.1:8767
```

Each command generates a temporary HTTPS URL.

Update `.env` with the generated URLs, appending `/mcp`:

```dotenv
ASSISTANT_MCP_URL=https://your-assistant-tunnel.trycloudflare.com/mcp
PAYMENTS_MCP_URL=https://your-payments-tunnel.trycloudflare.com/mcp
```

Keep both tunnels running while using the application.

Cloudflare Quick Tunnel URLs may change when restarted. If the URLs change, update `.env` and rerun the application startup script to register the new endpoints.

**Note:** Cloudflare tunnels are managed separately from `start.sh`. The local MCP servers will become reachable through the tunnels after the application starts.

If your Rakazo environment supports local HTTP MCP endpoints, Cloudflare can be skipped. For Docker-based Rakazo, the default local endpoints are:

```dotenv
ASSISTANT_MCP_URL=http://host.docker.internal:8766/mcp
PAYMENTS_MCP_URL=http://host.docker.internal:8767/mcp
```

## 5. Start the Application

After configuring `.env` and starting any required Cloudflare tunnels, run:

```bash
chmod +x start.sh
./start.sh
```

The script automatically:

1. Validates required environment variables and local ports.
2. Starts the Payments MCP server.
3. Starts the Payments A2A gateway.
4. Starts the Assistant MCP server.
5. Waits for the local servers to become available.
6. Runs `connect_mcp.py` to register the configured MCP endpoints in Rakazo.

A successful startup produces output similar to:

```text
Environment and port checks passed.
Waiting for local servers (logs: traces/demo/)...
Local servers are listening.
Registering MCP endpoints in Rakazo...
...
Ready. Open the Assistant chat in Rakazo.
Press Ctrl+C to stop all three local servers.
Logs: traces/demo/
```

The exact registration output depends on `connect_mcp.py`.

Keep the terminal running while using the application.

Press `Ctrl+C` to stop the three local servers. Cloudflare tunnels must be stopped separately.

### Application Architecture

```text
User
  |
  v
Assistant Agent (Rakazo)
  |
  v
Assistant MCP Server
  |
  v
Payments A2A Gateway
  |
  v
Payments Agent (Rakazo)
  |
  v
Payments MCP Server
  |
  v
Mock Banking Data
```

The Assistant agent requests verification through the A2A gateway. The Payments agent performs recipient and limit checks using its MCP tools.

## 6. Example Usage

Open the `Assistant` bot chat in Rakazo.

Enter the following message:

```text
Check whether a $500 transfer to mom is allowed.
```

The Assistant should request verification from Payments and return the result without executing a transfer.

The actual response depends on the current mock banking data and agent behavior.

You can also test the A2A gateway directly:

```bash
.venv/bin/python a2a/test_payments_a2a.py
```

Tool calls and inter-agent events are recorded in `traces/tool_log.jsonl` by default.

### Automatic JSON traces

`./start.sh` also starts a read-only Rakazo conversation watcher. Once the script
prints `Ready`, use the Assistant chat normally. Each new user text request
creates `traces/phase1/request-<uuid>.json`; the same file updates as conversation
messages and local tool events arrive. No timestamp or export command is needed.
It includes the original request, the Rakazo root `run_id`, local tool calls,
A2A messages, and Assistant/Payments conversation messages.

The watcher polls every two seconds. Existing conversations at watcher startup
are skipped; observed messages are cached while the watcher runs. Only messages
returned by the API can be captured; older pages are not fetched. Restarting the
watcher does not resume previous request files. `ASSISTANT_BOT_ID` is optional:
otherwise the watcher finds the bot named `Assistant`.

Files are live snapshots, not completion certificates: `collection_status` is
`watching` until the next user request closes the window
(`next_request_observed`). Stopping `start.sh` leaves the latest saved snapshot.
Local tools and Payments messages are associated by time window, so run one
request at a time and wait for the reply before sending the next one. The
exporter does not infer a final response or model reasoning. Watcher operational
logs are in `traces/demo/trace-watcher.log`.

### Manual export (optional)

Export a scenario's time window as one JSON file. Record the start time before
running the scenario, then export after the bots have finished responding:

```bash
TRACE_START=$(date -u +%Y-%m-%dT%H:%M:%SZ)
# Run your scenario in Rakazo, wait for its final response, then:
.venv/bin/python export_trace.py \
  --scenario S1 \
  --request 'Check whether a $500 transfer to mom is allowed.' \
  --since "$TRACE_START" \
  --with-rakazo \
  --output traces/S1.json
```

`--with-rakazo` reads the Assistant and Payments conversation snapshots using
`ASSISTANT_BOT_ID`, `PAYMENTS_BOT_ID`, and the existing Rakazo credentials in
`.env`. It does not send a new request. Omit it to export local logs only.
The export includes `events`, `tool_calls`, `messages`, and `rakazo_threads`.
The original request is supplied through `--request`; bot replies come from
the conversation snapshots. Existing output files are not overwritten.

Collection uses timestamps, not end-to-end run correlation: avoid overlapping
scenarios in the same window. Original `request_id` and `runId` values are kept;
`export_id` identifies the export only. Rakazo snapshots may omit older messages
because the exporter does not fetch older pages (`olderCursor` is preserved).
Use `--until` with an ISO timestamp and timezone to set an explicit end time.

## 7. Offline Tests

Trace records include a `request_id`. Assistant verification calls pass this ID
through A2A metadata, linking the Assistant tool result and gateway messages.
Independent MCP calls receive their own IDs. The live Rakazo → Payments MCP hop
does not currently propagate the parent ID; those records cannot yet be grouped
under the original verification request. IDs correlate logs, not authorization.

Run the offline verification flow (Assistant tool → in-process A2A gateway →
simulated Payments bot → real local bank lookup tools):

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_verification_offline.py' -v
```

These four tests cover eligible and blocked requests, bot failures, and JSONL
trace output. They block network connections, use temporary bank data and logs,
and verify that no transfer executes. Model decisions are simulated, so this
does not establish that a live LLM follows the policies.

Offline tests do not require Rakazo, Docker, or LLM API calls once Python dependencies are installed.

Run all tests:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Run policy counterexamples:

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_policy_offline.py' -v
```

The policy suite includes four known expected failures:

- **P1:** Missing explicit user confirmation before transfer execution
- **P2:** Missing additional verification for suspicious or unregistered recipients
- **P3:** Daily transfer limit not enforced at execution
- **P6:** Raw SMS content forwarded to Payments

These expected failures illustrate security limitations in the Phase 1 implementation.

For a basic read-only MCP smoke test:

```bash
.venv/bin/python client.py
```

## 8. Limitations

This project is a Phase 1 prototype for studying security risks in multi-agent financial workflows.

- All banking information is simulated using local fixtures in `data/`.
- `execute_transfer` modifies the local mock banking file, not a real account.
- User confirmation, additional verification, provenance tracking, and daily transfer limits are not fully enforced at the transfer execution boundary.
- Agent instructions alone do not guarantee compliance with security policies.
- Cloudflare Quick Tunnel URLs are temporary and must be updated when they change.

See `policy.md` for the intended security requirements and `episodes/` for example scenarios.

## 9. Troubleshooting

| Problem | Solution |
|---|---|
| Missing environment variables | Check `.env` against `.env.example` |
| Port already in use | Stop existing servers or change the configured port |
| MCP tool not available | Check MCP registration and restart the application |
| Cloudflare 502 error | Verify the local MCP server and corresponding tunnel |
| A2A verification timeout | Check `PAYMENTS_BOT_ID`, Rakazo connectivity, and gateway logs |

View server logs:

```bash
tail -f traces/demo/*.log
```

View tool execution traces:

```bash
tail -f traces/tool_log.jsonl
```

Stop Rakazo:

```bash
bash rakazo/setup-rakazo.sh stop
```

**Note:** `data/bank.json` is not automatically reset between application runs.

For additional demonstration instructions, see `RUN_GUIDE.md`.
