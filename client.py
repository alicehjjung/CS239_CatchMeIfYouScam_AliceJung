"""Test both Assistant and Payments MCP servers."""

import asyncio
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def unpack(result):
    if result.is_error:
        raise RuntimeError(str(result.content))

    return (
        result.structured_content
        or json.loads(result.content[0].text)
    )


async def demo():
    results = {}

    # 1. Assistant MCP Server
    assistant_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_servers.assistant_server"]
    )

    async with stdio_client(assistant_params) as (read, write):
        async with ClientSession(read, write) as client:
            await client.initialize()

            listed = (await client.list_tools()).tools

            inbox = await client.call_tool("read_inbox", {})
            payees = await client.call_tool("list_payees", {})

            results["assistant"] = {
                "tools": [tool.name for tool in listed],
                "inbox": unpack(inbox),
                "payees": unpack(payees)
            }

    # 2. Bank MCP Server
    bank_params = StdioServerParameters(
        command=sys.executable,
                args=["-m", "mcp_servers.payments_server"]
    )

    async with stdio_client(bank_params) as (read, write):
        async with ClientSession(read, write) as client:
            await client.initialize()

            listed = (await client.list_tools()).tools

            recipient = await client.call_tool(
                "lookup_recipient",
                {"recipient_id": "payee_01"}
            )

            limit = await client.call_tool(
                "check_daily_limit",
                {"amount": 50}
            )

            results["bank"] = {
                "tools": [tool.name for tool in listed],
                "recipient": unpack(recipient),
                "limit": unpack(limit)
            }

    return results


if __name__ == "__main__":
    print(json.dumps(asyncio.run(demo()), indent=2))
