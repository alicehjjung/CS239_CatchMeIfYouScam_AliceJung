"""Shared logger for the MCP servers and the A2A gateway. One JSONL file.

Record types:
  tool_call: {"type","ts","agent","tool","args","result"}
  message:   {"type","ts","from","to","content"}
"""
import json
import os
import time
import inspect
from contextvars import ContextVar
from functools import wraps
from uuid import uuid4
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")
LOG_PATH = Path(os.environ.get("TOOL_LOG") or "traces/tool_log.jsonl").expanduser()
if not LOG_PATH.is_absolute():
    LOG_PATH = PROJECT_ROOT / LOG_PATH

request_id = ContextVar("tool_request_id", default=None)


def traced_request(function):
    """Reuse the current request ID, or scope a new ID to one tool call."""
    if inspect.iscoroutinefunction(function):
        @wraps(function)
        async def asynchronous(*args, **kwargs):
            token = request_id.set(request_id.get() or str(uuid4()))
            try:
                return await function(*args, **kwargs)
            finally:
                request_id.reset(token)
        return asynchronous
    @wraps(function)
    def synchronous(*args, **kwargs):
        token = request_id.set(request_id.get() or str(uuid4()))
        try:
            return function(*args, **kwargs)
        finally:
            request_id.reset(token)
    return synchronous


def traced_a2a(function):
    @wraps(function)
    async def wrapped(self, context, event_queue):
        incoming = (getattr(context, "metadata", None) or {}).get("request_id")
        token = request_id.set(incoming if isinstance(incoming, str) and incoming else str(uuid4()))
        try:
            return await function(self, context, event_queue)
        finally:
            request_id.reset(token)
    return wrapped


def _write(record):
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": round(time.time(), 3),
                            "request_id": request_id.get() or str(uuid4()),
                            **record}, ensure_ascii=False) + "\n")


def log_call(agent, tool, args, result):
    """Record one tool call and return `result` unchanged, so it can wrap a `return`."""
    _write({"type": "tool_call", "agent": agent, "tool": tool, "args": args, "result": result})
    return result


def log_message(sender, receiver, content):
    """Record one inter-agent message (e.g. the A2A hop)."""
    _write({"type": "message", "from": sender, "to": receiver, "content": content})
