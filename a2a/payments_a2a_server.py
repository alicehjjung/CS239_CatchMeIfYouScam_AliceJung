import argparse
import asyncio
import logging
import os
import sys
import time
from pathlib import Path
import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "mcp_servers"))  # shared logger
from dotenv import load_dotenv
from rakazo.rakazo import Rakazo
from tool_log import log_message, traced_a2a

from a2a.helpers import (
    get_message_text,
    new_task_from_user_message,
    new_text_message,
    new_text_part,
)
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.types import (
    AgentCard,
    AgentCapabilities,
    AgentInterface,
    AgentSkill,
    TaskState,
)
from starlette.applications import Starlette


def ask_payments(request_text, timeout=120):
    """Send a request to Payments Bot and wait for its response."""
    load_dotenv()

    bot_id = os.environ["PAYMENTS_BOT_ID"]

    with Rakazo(
        os.environ["RAKAZO_URL"],
        origin=os.environ["RAKAZO_ORIGIN"],
    ) as client:
        client.login(
            os.environ["RAKAZO_EMAIL"],
            os.environ["RAKAZO_PASSWORD"],
        )

        result = client.send(bot_id, request_text)
        run_id = result["runId"]

        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:
            conversation = client.conversation(bot_id)

            for message in reversed(conversation["messages"]):
                if message.get("runId") != run_id:
                    continue

                if message.get("role") != "bot":
                    continue

                text = "\n".join(
                    block["text"]
                    for block in message.get("blocks", [])
                    if block.get("kind") == "text" and block.get("text")
                )

                if text.strip():
                    return text

            time.sleep(0.5)

        raise TimeoutError("Payments Bot response timed out.")


class PaymentsExecutor(AgentExecutor):
    def __init__(self, responder=ask_payments):
        self.responder = responder
        # Rakazo exposes one shared conversation per bot.
        self._lock = asyncio.Lock()

    @traced_a2a
    async def execute(self, context: RequestContext, event_queue: EventQueue):
        task = context.current_task or new_task_from_user_message(context.message)

        if context.current_task is None:
            await event_queue.enqueue_event(task)

        updater = TaskUpdater(
            event_queue=event_queue,
            task_id=task.id,
            context_id=task.context_id,
        )

        await updater.update_status(TaskState.TASK_STATE_WORKING)

        request_text = get_message_text(context.message)
        print(f"A2A: Payments received request: {request_text}", flush=True)
        # Exactly what arrived at Payments (the Assistant -> Payments message).
        log_message("assistant", "payments", request_text)

        try:
            if not request_text.strip():
                raise ValueError("A text request is required.")
            async with self._lock:
                response = await asyncio.to_thread(self.responder, request_text)
        except Exception as exc:
            logging.getLogger(__name__).warning("Payments request failed")
            # Log only the exception type: messages can contain credentials or URLs.
            log_message("payments", "assistant", {"error": type(exc).__name__})
            await updater.update_status(
                TaskState.TASK_STATE_FAILED,
                message=new_text_message(
                    "Payments Bot request failed. Check Rakazo connectivity, "
                    "credentials, bot ID, and response timeout."
                ),
            )
            return

        # Payments' final answer, before the Assistant summarizes it.
        log_message("payments", "assistant", response)
        await updater.add_artifact(
            parts=[new_text_part(text=response, media_type="text/plain")]
        )
        await updater.update_status(
            TaskState.TASK_STATE_COMPLETED,
            message=new_text_message("Request processed."),
        )

    async def cancel(self, context, event_queue):
        raise NotImplementedError("Cancellation is not supported.")


def make_app(port):
    card = AgentCard(
        name="Fraud Guard Payments",
        description="Bank-side payment verification agent.",
        version="1.0.0",
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        capabilities=AgentCapabilities(streaming=False),
        supported_interfaces=[
            AgentInterface(
                protocol_binding="JSONRPC",
                url=os.environ["PAYMENTS_A2A_URL"].rstrip("/") + "/",
                protocol_version="1.0",
            )
        ],
        skills=[
            AgentSkill(
                id="verify-payment",
                name="Verify payment",
                description="Review payment requests before execution.",
                tags=["payments", "fraud-prevention"],
            )
        ],
    )

    handler = DefaultRequestHandler(
        agent_executor=PaymentsExecutor(),
        task_store=InMemoryTaskStore(),
        agent_card=card,
    )

    return Starlette(
        routes=create_agent_card_routes(card)
        + create_jsonrpc_routes(handler, "/")
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=os.environ["PAYMENTS_A2A_HOST"])
    parser.add_argument("--port", type=int, default=int(os.environ["PAYMENTS_A2A_PORT"]))
    args = parser.parse_args()

    uvicorn.run(
        make_app(args.port),
        host=args.host,
        port=args.port,
    )
