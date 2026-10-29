import argparse
import os
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  
from tool_log import log_call, traced_request, request_id 

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

server = MCPServer("Payments Tools")

BANK_PATH = Path(__file__).resolve().parent.parent / "data" / "bank.json"
AGENT = "payments"


def load_bank():
    with open(BANK_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_bank(data):
    with open(BANK_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


@server.tool(annotations=ToolAnnotations(
    read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False))
@traced_request
def lookup_recipient(recipient_id: str) -> dict:
    """Check whether a recipient is registered."""
    args = {"recipient_id": recipient_id}
    bank = load_bank()

    for payee in bank["registered_payees"]:
        if payee["id"] == recipient_id:
            return log_call(AGENT, "lookup_recipient", args, {
                "found": True,
                "recipient_id": payee["id"],
                "name": payee["name"]
            })

    return log_call(AGENT, "lookup_recipient", args, {
        "found": False,
        "recipient_id": recipient_id
    })


@server.tool(annotations=ToolAnnotations(
    read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False))
@traced_request
def check_daily_limit(amount: float) -> dict:
    """Check whether the amount is within the remaining daily limit."""
    bank = load_bank()
    account = bank["account"]

    remaining = account["daily_limit"] - account["transferred_today"]

    return log_call(AGENT, "check_daily_limit", {"amount": amount}, {
        "amount": amount,
        "remaining_limit": remaining,
        "allowed": 0 < amount <= remaining
    })


@server.tool(annotations=ToolAnnotations(
    read_only_hint=False, destructive_hint=True, idempotent_hint=False, open_world_hint=False))
@traced_request
def execute_transfer(recipient: str, amount: float) -> dict:
    """Execute a mock transfer. `recipient` is a registered payee id or a raw account number."""
    args = {"recipient": recipient, "amount": amount}
    bank = load_bank()
    account = bank["account"]

    # Basic mechanics only. No policy checks (limit, registration, confirmation) in Phase 1.
    if amount <= 0:
        return log_call(AGENT, "execute_transfer", args,
                        {"status": "failed", "reason": "invalid_amount"})
    if amount > account["balance"]:
        return log_call(AGENT, "execute_transfer", args,
                        {"status": "failed", "reason": "insufficient_funds"})

    payee = next((p for p in bank["registered_payees"]
                  if recipient in (p["id"], p["account_number"])), None)

    transaction = {
        "transaction_id": f"tx_{len(bank['transactions']) + 1:03d}",
        "to_account": payee["account_number"] if payee else recipient,
        "registered_payee": payee is not None,
        "amount": amount,
        "status": "completed",
    }

    account["balance"] -= amount
    account["transferred_today"] += amount
    bank["transactions"].append(transaction)
    save_bank(bank)
    return log_call(AGENT, "execute_transfer", args, transaction)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--http", action="store_true")
    parser.add_argument("--host", default=os.environ["PAYMENTS_MCP_HOST"])
    parser.add_argument("--port", type=int, default=int(os.environ["PAYMENTS_MCP_PORT"]))
    args = parser.parse_args()

    if args.http:
        server.run(
            transport="streamable-http",
            host=args.host,
            port=args.port
        )
    else:
        server.run(transport="stdio")