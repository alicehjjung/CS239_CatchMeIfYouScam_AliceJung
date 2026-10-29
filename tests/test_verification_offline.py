"""Offline verification flow with real A2A serialization and local bank tools.

Only the model's decision-making is simulated. No sockets, hosted LLMs, Rakazo,
or startup scripts are used. All bank data and traces are temporary.
"""
import importlib.util
import json
import os
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

import httpx
import tool_log
from mcp_servers import assistant_server as assistant
from mcp_servers import payments_server as payments

spec = importlib.util.spec_from_file_location(
    "offline_verification_gateway",
    Path(__file__).resolve().parents[1] / "a2a/payments_a2a_server.py",
)
gateway = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gateway)


class OfflineVerificationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.bank_path = Path(temporary.name) / "bank.json"
        self.trace_path = Path(temporary.name) / "trace.jsonl"
        self.bank_path.write_text(json.dumps({
            "account": {"balance": 5000, "daily_limit": 1000, "transferred_today": 100},
            "registered_payees": [
                {"id": "payee_01", "name": "Test Payee", "account_number": "111122223333"}
            ],
            "transactions": [],
        }), encoding="utf-8")
        self.original_bank = self.bank_path.read_bytes()
        for override in (
            patch.object(payments, "BANK_PATH", self.bank_path),
            patch.object(tool_log, "LOG_PATH", self.trace_path),
            patch.dict(os.environ, {"PAYMENTS_A2A_URL": "http://offline.test"}),
            patch.object(socket, "create_connection", side_effect=AssertionError("Network forbidden")),
            patch.object(socket.socket, "connect", side_effect=AssertionError("Network forbidden")),
        ):
            override.start()
            self.addCleanup(override.stop)

    async def invoke(self, recipient, amount, responder=None):
        def simulated_bot(text):
            # Deterministic substitute for model inference, not an authorization engine.
            self.assertIn("Verification only. Do not execute any transfer.", text)
            found = payments.lookup_recipient(recipient)["found"]
            within_limit = payments.check_daily_limit(amount)["allowed"]
            return "Eligible for further authorization" if found and within_limit else "Blocked"

        executor = gateway.PaymentsExecutor(responder or simulated_bot)
        with patch.object(gateway, "PaymentsExecutor", return_value=executor):
            app = gateway.make_app(9999)
        client_class = httpx.AsyncClient

        def offline_client(**kwargs):
            return client_class(transport=httpx.ASGITransport(app=app), **kwargs)

        with patch.object(assistant.httpx, "AsyncClient", side_effect=offline_client):
            with patch.object(payments, "execute_transfer") as execute:
                result = await assistant.request_payment_verification(
                    f"Verify ${amount} to {recipient}."
                )
                execute.assert_not_called()
        self.assertEqual(self.bank_path.read_bytes(), self.original_bank)
        records = [json.loads(line) for line in self.trace_path.read_text().splitlines()]
        self.assertEqual(records[-1]["tool"], "request_payment_verification")
        self.assertEqual(records[-1]["result"], result)
        self.assertTrue(records[-1]["request_id"])
        self.assertEqual(len({record["request_id"] for record in records}), 1)
        return result, records

    async def test_registered_recipient_within_limit_and_trace(self):
        result, records = await self.invoke("payee_01", 500)
        self.assertEqual(result, {"verification_result": "Eligible for further authorization"})
        self.assertEqual([r["tool"] for r in records if r["type"] == "tool_call"],
                         ["lookup_recipient", "check_daily_limit", "request_payment_verification"])
        messages = [r for r in records if r["type"] == "message"]
        self.assertEqual([(r["from"], r["to"]) for r in messages],
                         [("assistant", "payments"), ("payments", "assistant")])
        self.assertEqual(messages[-1]["content"], result["verification_result"])

    async def test_unregistered_recipient(self):
        result, _ = await self.invoke("unknown_payee", 50)
        self.assertEqual(result, {"verification_result": "Blocked"})

    async def test_amount_above_remaining_daily_limit(self):
        result, _ = await self.invoke("payee_01", 950)
        self.assertEqual(result, {"verification_result": "Blocked"})

    async def test_bot_failure_returns_error_and_logs_exception_type(self):
        def fail(text):
            raise RuntimeError("private diagnostic details")
        result, records = await self.invoke("payee_01", 50, responder=fail)
        self.assertIn("error", result)
        self.assertNotIn("private diagnostic details", json.dumps(records))
        self.assertTrue(any(r.get("content") == {"error": "RuntimeError"} for r in records))


if __name__ == "__main__":
    unittest.main()
