"""Export local events and optional Rakazo conversation snapshots as JSON."""
import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from tool_log import LOG_PATH


def timestamp(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Include a timezone, for example 2026-10-29T16:00:00-07:00")
    return parsed.timestamp()


def build_trace(log_path, *, scenario, request, since, until, threads=None):
    if until < since:
        raise ValueError("until must be at or after since")
    events = []
    if log_path.exists():
        for number, line in enumerate(log_path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
                ts = float(event["ts"])
            except (ValueError, TypeError, KeyError) as exc:
                raise ValueError(f"Invalid trace event on line {number}") from exc
            if since <= ts <= until:
                events.append(event)
    conversations = {}
    for name, thread in (threads or {}).items():
        messages = [
            message for message in thread.get("messages", [])
            if message.get("createdAt")
            and since <= timestamp(message["createdAt"]) <= until
        ]
        conversations[name] = {
            "threadId": thread.get("threadId"),
            "messages": messages,
            "olderCursor": thread.get("olderCursor"),
        }
    return {
        "export_id": str(uuid4()),
        "scenario": scenario,
        "request": request,
        "started_at": datetime.fromtimestamp(since, timezone.utc).isoformat(),
        "ended_at": datetime.fromtimestamp(until, timezone.utc).isoformat(),
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "collection": {
            "method": "time_window",
            "notes": [
                "Events may include concurrent requests in this time window.",
                "Export ID is not a Rakazo run ID; original request_id/runId values are preserved.",
                "Conversation snapshots contain only messages returned by threads/get; older pages are not fetched.",
                "Missing conversation records do not establish that no conversation occurred.",
            ],
        },
        "events": events,
        "tool_calls": [event for event in events if event.get("type") == "tool_call"],
        "messages": [event for event in events if event.get("type") == "message"],
        "rakazo_threads": conversations,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--request", required=True, help="Original user request (provided by you)")
    parser.add_argument("--since", required=True, type=timestamp, help="ISO timestamp with timezone")
    parser.add_argument("--until", type=timestamp, default=None)
    parser.add_argument("--log", type=Path, default=LOG_PATH)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--with-rakazo", action="store_true", help="Read both bots' current conversations")
    args = parser.parse_args()
    until = args.until if args.until is not None else datetime.now(timezone.utc).timestamp()
    threads = {}
    if args.with_rakazo:
        from rakazo.rakazo import Rakazo

        with Rakazo(os.environ["RAKAZO_URL"], origin=os.environ["RAKAZO_ORIGIN"]) as client:
            client.login(os.environ["RAKAZO_EMAIL"], os.environ["RAKAZO_PASSWORD"])
            for name, key in (("assistant", "ASSISTANT_BOT_ID"), ("payments", "PAYMENTS_BOT_ID")):
                threads[name] = client.conversation(os.environ[key])
    trace = build_trace(args.log, scenario=args.scenario, request=args.request,
                        since=args.since, until=until, threads=threads)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as output:
        json.dump(trace, output, ensure_ascii=False, indent=2)
        output.write("\n")
    print(f"Saved {len(trace['events'])} local events to {args.output}")


if __name__ == "__main__":
    main()
