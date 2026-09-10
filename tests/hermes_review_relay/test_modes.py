import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def load_plugin():
    spec = importlib.util.spec_from_file_location(
        "paseo_review_relay",
        ROOT / "__init__.py",
        submodule_search_locations=[str(ROOT)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class SilentSender:
    def __init__(self):
        self.calls = []

    async def send(self, target, body):
        self.calls.append((target, body))
        return f"alert-{len(self.calls)}"


class ModeRequestTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.module = load_plugin()
        self.tmp = tempfile.TemporaryDirectory()
        self.store = self.module.Storage(Path(self.tmp.name) / "relay.sqlite3")
        self.sender = SilentSender()
        self.service = self.module.OutboundService(
            store=self.store,
            sender=self.sender,
            telegram_target="telegram:owner-chat",
        )

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def conversation(self, **changes):
        fields = {
            "decision_id": "conversation-1",
            "owner_agent_id": "agent-owner",
            "server_id": "server-vps",
            "mode": "conversation",
            "title": "Production deploy window",
            "question": "Deploy tonight?",
        }
        fields.update(changes)
        return self.module.DecisionRequest(**fields)

    async def test_absent_mode_keeps_legacy_request_in_pr_mode(self):
        request = self.module.DecisionRequest(
            decision_id="legacy-pr",
            owner_agent_id="agent-owner",
            server_id="server-vps",
            repository="acme/widgets",
            pr_number=42,
            head_sha="a" * 40,
            base_sha="b" * 40,
            proposal="Change policy",
            consequence="Sessions restart",
            recommendation="hold",
            question="Proceed?",
        )

        await self.service.open(request)

        decision = self.store.get_decision("legacy-pr")
        self.assertEqual(decision["mode"], "pr")
        self.assertIsNone(decision["context"])
        self.assertIn("acme/widgets#42", self.sender.calls[0][1])

    async def test_unknown_mode_is_rejected_before_persistence(self):
        request = self.conversation(mode="ticket")

        with self.assertRaisesRegex(ValueError, "mode"):
            await self.service.open(request)

        self.assertIsNone(self.store.get_decision("conversation-1"))
        self.assertEqual(self.sender.calls, [])

    async def test_conversation_requires_title_and_question(self):
        for field in ("title", "question"):
            with self.subTest(field=field):
                request = self.conversation(**{field: ""})
                with self.assertRaisesRegex(ValueError, field):
                    await self.service.open(request)
                self.assertEqual(self.sender.calls, [])

    async def test_conversation_rejects_every_pr_field(self):
        pr_fields = {
            "repository": "acme/widgets",
            "pr_number": 42,
            "head_sha": "a" * 40,
            "base_sha": "b" * 40,
        }
        for field, value in pr_fields.items():
            with self.subTest(field=field):
                request = self.conversation(**{field: value})
                with self.assertRaisesRegex(ValueError, "PR fields"):
                    await self.service.open(request)
                self.assertEqual(self.sender.calls, [])

    async def test_conversation_receipts_are_bounded_lowercase_words(self):
        invalid = (
            "approve",
            ["two words"],
            ["Approve"],
            ["ok1"],
            ["a", "b", "c", "d", "e", "f"],
        )
        for index, receipts in enumerate(invalid):
            with self.subTest(receipts=receipts):
                request = self.conversation(
                    decision_id=f"invalid-receipts-{index}", receipts=receipts
                )
                with self.assertRaisesRegex(ValueError, "receipts"):
                    await self.service.open(request)
                self.assertEqual(self.sender.calls, [])

        duplicate = self.conversation(receipts=["accept", "accept"])
        with self.assertRaisesRegex(ValueError, "unique"):
            await self.service.open(duplicate)
        self.assertEqual(self.sender.calls, [])

        valid = self.conversation(receipts=["accept", "decline"])
        await self.service.open(valid)
        self.assertIn("accept, decline", self.sender.calls[0][1])

    async def test_pr_mode_rejects_receipt_override(self):
        request = self.module.DecisionRequest(
            decision_id="pr-override",
            owner_agent_id="agent-owner",
            server_id="server-vps",
            repository="acme/widgets",
            pr_number=42,
            head_sha="a" * 40,
            base_sha="b" * 40,
            proposal="Change policy",
            consequence="Sessions restart",
            recommendation="hold",
            question="Proceed?",
            receipts=["approve"],
        )

        with self.assertRaisesRegex(ValueError, "receipts"):
            await self.service.open(request)

    async def test_context_must_be_a_string_map_with_a_2048_byte_limit(self):
        invalid = (
            [],
            {"ticket": 42},
            {42: "ENG-142"},
            {"note": "é" * 1024},
        )
        for index, context in enumerate(invalid):
            with self.subTest(context=context):
                request = self.conversation(
                    decision_id=f"invalid-context-{index}", context=context
                )
                with self.assertRaisesRegex(ValueError, "context"):
                    await self.service.open(request)
                self.assertEqual(self.sender.calls, [])

        boundary = self.conversation(
            decision_id="boundary-context", context={"x": "a" * 2040}
        )
        await self.service.open(boundary)
        valid = self.conversation(context={"ticket": "ENG-142"})
        await self.service.open(valid)
        self.assertIn('"ticket":"ENG-142"', self.store.get_decision("conversation-1")["context"])


if __name__ == "__main__":
    unittest.main()
