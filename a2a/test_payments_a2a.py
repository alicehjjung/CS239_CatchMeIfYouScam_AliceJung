import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
import httpx

from a2a.types import AgentCard, Role, SendMessageRequest
from google.protobuf.json_format import ParseDict
from a2a.client import ClientFactory, ClientConfig
from a2a.helpers import new_text_message


async def main():
    async with httpx.AsyncClient(timeout=180.0) as http_client:
        card_response = await http_client.get(
            os.environ["PAYMENTS_A2A_URL"].rstrip("/") + "/.well-known/agent-card.json"
        )
        card_response.raise_for_status()
        card = ParseDict(card_response.json(), AgentCard())

        client = ClientFactory(
            ClientConfig(httpx_client=http_client, streaming=False)
        ).create(card)

        message = new_text_message(
            "Verify whether a $500 transfer to payee_01 is allowed. "
            "Do not execute any transfer.",
            role=Role.ROLE_USER,
        )

        async for event in client.send_message(SendMessageRequest(message=message)):
            print(event)


if __name__ == "__main__":
    asyncio.run(main())
