"""Watch Rakazo conversations and save a JSON snapshot per new user request."""
import argparse
import json
import os
import time
from pathlib import Path
from uuid import uuid4

from export_trace import build_trace, timestamp
from rakazo.rakazo import Rakazo
from tool_log import LOG_PATH, PROJECT_ROOT


def user_request(message):
    """Exclude bot-to-bot messages represented with role=user by Rakazo."""
    if message.get("role") != "user":
        return None
    blocks = message.get("blocks", [])
    if any(block.get("kind") == "bot_message_received" for block in blocks):
        return None
    text = "\n".join(block["text"] for block in blocks
                     if block.get("kind") == "text" and block.get("text"))
    return text if text.strip() else None


class TraceWatcher:
    def __init__(self, log_path, output_dir):
        self.log_path = log_path
        self.output_dir = output_dir
        self.seen = set()
        self.threads = {}
        self.current = None
        self.last_content = None
        self.initialized = False

    def poll(self, snapshots, now):
        incoming = []
        for name, snapshot in snapshots.items():
            previous = self.threads.get(name, {})
            messages = {message["id"]: message for message in previous.get("messages", [])}
            for message in snapshot.get("messages", []):
                messages[message["id"]] = message
                if name == "assistant" and message["id"] not in self.seen:
                    self.seen.add(message["id"])
                    if self.initialized and user_request(message) is not None:
                        incoming.append(message)
            self.threads[name] = {
                "threadId": snapshot.get("threadId"),
                "olderCursor": snapshot.get("olderCursor"),
                "messages": sorted(messages.values(), key=lambda item: item["createdAt"]),
            }
        self.initialized = True
        for message in sorted(incoming, key=lambda item: item["createdAt"]):
            start = timestamp(message["createdAt"])
            if self.current:
                # Close the time window, without claiming that the bot run completed.
                self.save(start - 0.000001, "next_request_observed")
            self.current = {
                "id": str(uuid4()), "start": start,
                "request": user_request(message), "message_id": message["id"],
                "run_id": message.get("runId"),
            }
            self.last_content = None
        if self.current:
            self.save(now, "watching")

    def save(self, until, status):
        current = self.current
        trace = build_trace(self.log_path, scenario="automatic", request=current["request"],
                            since=current["start"], until=max(until, current["start"]),
                            threads=self.threads)
        trace.update(export_id=current["id"], run_id=current["run_id"],
                     request_message_id=current["message_id"], collection_status=status)
        trace["collection"]["notes"].append(
            "Automatic snapshots update until the next user request or watcher shutdown; "
            "collection_status does not indicate bot completion."
        )
        # Re-write only when captured content changes, not on every polling tick.
        content = json.dumps({key: value for key, value in trace.items()
                              if key not in ("ended_at", "exported_at")}, sort_keys=True)
        if content == self.last_content:
            return
        self.output_dir.mkdir(parents=True, exist_ok=True)
        path = self.output_dir / f"request-{current['id']}.json"
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(trace, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)
        self.last_content = content
        print(f"Trace saved: {path}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "traces" / "phase1")
    parser.add_argument("--ready-file", type=Path)
    args = parser.parse_args()
    watcher = TraceWatcher(LOG_PATH, args.output_dir)
    with Rakazo(os.environ["RAKAZO_URL"], origin=os.environ["RAKAZO_ORIGIN"]) as client:
        client.login(os.environ["RAKAZO_EMAIL"], os.environ["RAKAZO_PASSWORD"])
        bots = client.rpc("bots/list")
        assistant_id = os.getenv("ASSISTANT_BOT_ID") or next(
            bot["id"] for bot in bots if bot["name"] == "Assistant")
        bot_ids = {"assistant": assistant_id, "payments": os.environ["PAYMENTS_BOT_ID"]}
        ready = False
        while True:
            try:
                snapshots = {name: client.conversation(bot_id) for name, bot_id in bot_ids.items()}
                watcher.poll(snapshots, time.time())
                if not ready:
                    if args.ready_file:
                        args.ready_file.write_text("ready\n", encoding="utf-8")
                    print("Trace watcher ready. New Assistant requests will be saved automatically.", flush=True)
                    ready = True
            except Exception as exc:
                if not ready:
                    raise
                # No response bodies, URLs, or credentials in operational logs.
                print(f"Trace polling failed ({type(exc).__name__}); retrying.", flush=True)
            time.sleep(2)


if __name__ == "__main__":
    main()
