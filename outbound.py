import hashlib
import json
import uuid
from dataclasses import asdict, dataclass

from .adapters import AmbiguousDelivery, CommandFailure
from .modes import alert_body, answer_body, sanitize_request, storage_fields, validate_request


@dataclass(frozen=True)
class DecisionRequest:
    decision_id: str
    owner_agent_id: str
    server_id: str
    repository: str | None = None
    pr_number: int | None = None
    head_sha: str | None = None
    base_sha: str | None = None
    proposal: str = ""
    consequence: str = ""
    recommendation: str = ""
    question: str = ""
    demo: bool = False
    mode: str = "pr"
    title: str = ""
    receipts: list | None = None
    context: dict | None = None

    def proposal_digest(self):
        encoded = json.dumps(asdict(self), sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
        return hashlib.sha256(encoded).hexdigest()


class OutboundService:
    def __init__(self, *, store, sender, telegram_target):
        self.store = store
        self.sender = sender
        self.telegram_target = telegram_target

    async def open(self, request):
        validate_request(request)
        request = sanitize_request(request)
        digest = request.proposal_digest()
        identity = storage_fields(request)
        self.store.open_decision(
            decision_id=request.decision_id,
            owner_agent_id=request.owner_agent_id,
            server_id=request.server_id,
            proposal_digest=digest,
            demo=request.demo,
            **identity,
        )
        body = alert_body(request, digest)
        attempt_id = str(uuid.uuid4())
        self.store.create_outbound_attempt(
            attempt_id, request.decision_id, "alert", body
        )
        try:
            message_id = await self.sender.send(self.telegram_target, body)
        except AmbiguousDelivery:
            self.store.mark_outbound_state(attempt_id, "uncertain")
            self.store.set_decision_status(request.decision_id, "uncertain")
            raise
        except CommandFailure:
            self.store.mark_outbound_state(attempt_id, "failed")
            raise
        self.store.mark_outbound_sent(
            attempt_id,
            "telegram",
            self.telegram_target.removeprefix("telegram:"),
            message_id,
        )
        return {"attempt_id": attempt_id, "message_id": str(message_id)}

    async def retry_failed(self, failed_attempt_id):
        failed = self.store.get_outbound_attempt(failed_attempt_id)
        if failed is None or failed["state"] != "failed":
            raise ValueError("only a definite failed attempt may be retried")
        decision = self.store.get_decision(failed["decision_id"])
        if decision is None or decision["status"] != "open":
            raise ValueError("retry requires an open decision")
        attempt_id = str(uuid.uuid4())
        self.store.create_outbound_attempt(
            attempt_id,
            failed["decision_id"],
            failed["kind"],
            failed["body"],
            retry_of=failed_attempt_id,
        )
        try:
            message_id = await self.sender.send(self.telegram_target, failed["body"])
        except AmbiguousDelivery:
            self.store.mark_outbound_state(attempt_id, "uncertain")
            self.store.set_decision_status(failed["decision_id"], "uncertain")
            raise
        except CommandFailure:
            self.store.mark_outbound_state(attempt_id, "failed")
            raise
        self.store.mark_outbound_sent(
            attempt_id,
            "telegram",
            self.telegram_target.removeprefix("telegram:"),
            message_id,
        )
        return {"attempt_id": attempt_id, "message_id": str(message_id)}

    async def publish_answer(self, decision_id, answer):
        decision = self.store.get_decision(decision_id)
        if decision is None or decision["status"] != "open":
            raise ValueError("answers require an open decision")
        body = answer_body(decision, answer)
        attempt_id = str(uuid.uuid4())
        self.store.create_outbound_attempt(attempt_id, decision_id, "answer", body)
        try:
            message_id = await self.sender.send(self.telegram_target, body)
        except AmbiguousDelivery:
            self.store.mark_outbound_state(attempt_id, "uncertain")
            self.store.set_decision_status(decision_id, "uncertain")
            raise
        except CommandFailure:
            self.store.mark_outbound_state(attempt_id, "failed")
            raise
        self.store.mark_outbound_sent(
            attempt_id,
            "telegram",
            self.telegram_target.removeprefix("telegram:"),
            message_id,
        )
        return {"attempt_id": attempt_id, "message_id": str(message_id)}

    async def supersede(self, old_decision_id, request):
        validate_request(request)
        request = sanitize_request(request)
        digest = request.proposal_digest()
        identity = storage_fields(request)
        self.store.supersede_decision(
            old_decision_id,
            decision_id=request.decision_id,
            owner_agent_id=request.owner_agent_id,
            server_id=request.server_id,
            proposal_digest=digest,
            demo=request.demo,
            **identity,
        )
        body = alert_body(request, digest)
        attempt_id = str(uuid.uuid4())
        self.store.create_outbound_attempt(
            attempt_id, request.decision_id, "alert", body
        )
        try:
            message_id = await self.sender.send(self.telegram_target, body)
        except AmbiguousDelivery:
            self.store.mark_outbound_state(attempt_id, "uncertain")
            self.store.set_decision_status(request.decision_id, "uncertain")
            raise
        except CommandFailure:
            self.store.mark_outbound_state(attempt_id, "failed")
            raise
        self.store.mark_outbound_sent(
            attempt_id,
            "telegram",
            self.telegram_target.removeprefix("telegram:"),
            message_id,
        )
        return {"attempt_id": attempt_id, "message_id": str(message_id)}
