import os
from dotenv import load_dotenv
from rakazo.rakazo import Rakazo

load_dotenv(override=True)

PAYMENTS_BOT_ID = os.environ["PAYMENTS_BOT_ID"]

with Rakazo(
    os.environ["RAKAZO_URL"],
    origin=os.environ["RAKAZO_ORIGIN"],
) as client:
    client.login(
        os.environ["RAKAZO_EMAIL"],
        os.environ["RAKAZO_PASSWORD"],
    )

    result = client.send(
        PAYMENTS_BOT_ID,
        "Hello Payments. Please introduce yourself. Do not use any tools.",
    )

    print(result)

    conversation = client.conversation(PAYMENTS_BOT_ID)
    print("Type:", type(conversation))

    for message in reversed(conversation["messages"]):
        if message["role"] == "bot":
            for block in message.get("blocks", []):
                if block.get("kind") == "text":
                    print(block["text"])
            break
