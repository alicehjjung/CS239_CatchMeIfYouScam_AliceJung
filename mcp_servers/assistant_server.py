import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1])) 
from tool_log import log_call, traced_request, request_id 

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

import os

import httpx
from dotenv import load_dotenv
from google.protobuf.json_format import ParseDict
from a2a.client import ClientFactory, ClientConfig
from a2a.helpers import new_text_message
from a2a.types import AgentCard, Role, SendMessageRequest, TaskState

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

server = MCPServer("Assistant Tools")

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
AGENT = "assistant"


@server.tool(annotations=ToolAnnotations(
    read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False))
@traced_request
def read_inbox() -> dict:
    """Read messages from the user's inbox."""
    # stderr, not stdout: stdout carries the protocol in stdio mode.
    print("MCP: read_inbox called", file=sys.stderr, flush=True)
    with open(DATA_DIR / "messages.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    return log_call(AGENT, "read_inbox", {}, {"messages": data["messages"]})


@server.tool(annotations=ToolAnnotations(
    read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False))
@traced_request
def list_payees() -> dict:
    """List registered payees without exposing full account numbers."""
    print("MCP: list_payees called", file=sys.stderr, flush=True)
    with open(DATA_DIR / "bank.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    payees = [
        {
            "id": payee["id"],
            "name": payee["name"],
            "account_masked": "****" + payee["account_number"][-4:]
        }
        for payee in data["registered_payees"]
    ]

    return log_call(AGENT, "list_payees", {}, {"payees": payees})


async def call_payments_a2a(request_text: str) -> str:
    """Send a verification request to Payments via A2A."""
    url = os.environ["PAYMENTS_A2A_URL"].rstrip("/")

    async with httpx.AsyncClient(timeout=180.0) as http_client:
        response = await http_client.get(
            f"{url}/.well-known/agent-card.json"
        )
        response.raise_for_status()

        card = ParseDict(response.json(), AgentCard())

        client = ClientFactory(
            ClientConfig(httpx_client=http_client, streaming=False)
        ).create(card)

        message = new_text_message(
            request_text,
            role=Role.ROLE_USER,
        )

        result_texts = []

        async for event in client.send_message(
            SendMessageRequest(message=message, metadata={"request_id": request_id.get() or ""})
        ):
            if event.HasField("task"):
                task = event.task
                if task.status.state != TaskState.TASK_STATE_COMPLETED:
                    detail = " ".join(
                        part.text for part in task.status.message.parts
                        if part.HasField("text")
                    )
                    raise RuntimeError(detail or "Payments verification did not complete.")
                for artifact in task.artifacts:
                    for part in artifact.parts:
                        if part.HasField("text"):
                            result_texts.append(part.text)
            elif event.HasField("message"):
                result_texts.extend(
                    part.text for part in event.message.parts if part.HasField("text")
                )
        if not any(text.strip() for text in result_texts):
            raise RuntimeError("Payments returned no verification text.")
        return "\n".join(result_texts)


@server.tool(annotations=ToolAnnotations(
    read_only_hint=True,
    destructive_hint=False,
    idempotent_hint=False,
    open_world_hint=True,
))
@traced_request
async def request_payment_verification(request_text: str) -> dict:
    """Ask the independent Payments agent to verify a transfer via A2A.

    Verification only. Never request or execute a transfer.
    """
    print("MCP: request_payment_verification called", file=sys.stderr, flush=True)

    # This tool is the inter-agent message (Assistant -> Payments), so the full text
    # that is actually sent is logged: it is the evidence for information-isolation checks.
    if not request_text.strip():
        return log_call(AGENT, "request_payment_verification",
                        {"request_text": request_text},
                        {"error": "A verification request is required."})

    safe_request = (
        "Verification only. Do not execute any transfer.\n"
        + request_text
    )
    args = {"request_text": request_text, "sent_to_payments": safe_request}

    try:
        result = await call_payments_a2a(safe_request)
        return log_call(AGENT, "request_payment_verification", args,
                        {"verification_result": result})
    except Exception as exc:
        return log_call(AGENT, "request_payment_verification", args,
                        {"error": f"A2A verification failed: {type(exc).__name__}"})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--http", action="store_true")
    parser.add_argument("--host", default=os.environ["ASSISTANT_MCP_HOST"])
    parser.add_argument("--port", type=int, default=int(os.environ["ASSISTANT_MCP_PORT"]))
    args = parser.parse_args()

    if args.http:
        server.run(
            transport="streamable-http",
            host=args.host,
            port=args.port
        )
    else:
        server.run(transport="stdio")
