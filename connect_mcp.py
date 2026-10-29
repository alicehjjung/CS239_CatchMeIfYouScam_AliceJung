import os
from rakazo.rakazo import Rakazo
from dotenv import load_dotenv

load_dotenv(override=True)

RAKAZO_URL = os.environ["RAKAZO_URL"]
ASSISTANT_MCP_URL = os.environ["ASSISTANT_MCP_URL"]
PAYMENTS_MCP_URL = os.environ["PAYMENTS_MCP_URL"]

def connect_mcp(client, bot_name, server_name, slug, endpoint):
    # Find existing bot
    bots = client.rpc("bots/list")
    bot = next((b for b in bots if b["name"] == bot_name), None)

    if bot is None:
        raise RuntimeError(f"Bot not found: {bot_name}")

    # Find or create MCP server
    servers = client.rpc("mcp/servers/list")
    server = next((s for s in servers if s["slug"] == slug), None)

    if server is None:
        server = client.rpc(
            "mcp/servers/create",
            {
                "name": server_name,
                "slug": slug,
                "endpoint": endpoint,
                "transport": "streamable_http",
            },
        )
    elif server["endpoint"] != endpoint:
        print(f"Endpoint changed for {slug}")

        response = client.http.post(
            "/rpc/mcp/servers/update",
            json={
                "json": {
                    "id": server["id"],
                    "config": {
                        "name": server_name,
                        "slug": slug,
                        "endpoint": endpoint,
                        "transport": "streamable_http",
                    },
                }
            },
        )

        if not response.is_success:
            print("Update error:", response.text)
            raise RuntimeError("MCP endpoint update failed")

        print(f"Updated endpoint for {slug}")

    # Assign MCP server to bot
    client.rpc(
        "mcp/assignments/approve",
        {
            "botId": bot["id"],
            "serverId": server["id"],
        },
    )

    print(f"Success! {bot_name} MCP server connected.")


with Rakazo(
    RAKAZO_URL,
    origin=os.environ["RAKAZO_ORIGIN"],
) as client:
    client.login(
        os.environ["RAKAZO_EMAIL"],
        os.environ["RAKAZO_PASSWORD"],
    )

    connect_mcp(
        client,
        "Assistant",
        "Assistant Tools",
        "assistant-tools",
        ASSISTANT_MCP_URL,
    )

    connect_mcp(
        client,
        "Payments",
        "Payments Tools",
        "payments-tools",
        PAYMENTS_MCP_URL,
    )
