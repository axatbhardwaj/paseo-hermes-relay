import json
import re
from dataclasses import dataclass, replace


PR_MODE = "pr"
CONVERSATION_MODE = "conversation"
MODES = frozenset({PR_MODE, CONVERSATION_MODE})
PR_RECEIPTS = frozenset({"approve", "reject", "hold"})
CONTEXT_LIMIT_BYTES = 2048
RECEIPT_PATTERN = re.compile(r"[a-z]+\Z")


@dataclass(frozen=True)
class StoredMode:
    name: str
    title: str = ""
    receipts: frozenset = frozenset()
    context: dict | None = None


def canonical_json(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _require_non_empty_string(value, field):
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string")


def _validate_context(context):
    if not isinstance(context, dict) or any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in context.items()
    ):
        raise ValueError("context must be an object with string keys and values")
    if len(canonical_json(context).encode("utf-8")) > CONTEXT_LIMIT_BYTES:
        raise ValueError("context canonical JSON must be at most 2048 UTF-8 bytes")


def _validate_receipts(receipts):
    if (
        not isinstance(receipts, list)
        or not 1 <= len(receipts) <= 5
        or any(
            not isinstance(word, str) or RECEIPT_PATTERN.fullmatch(word) is None
            for word in receipts
        )
        or len(set(receipts)) != len(receipts)
    ):
        raise ValueError(
            "receipts must contain one to five unique lowercase ASCII words"
        )


def validate_request(request):
    for field in ("decision_id", "owner_agent_id", "server_id"):
        _require_non_empty_string(getattr(request, field), field)
    if not isinstance(request.mode, str) or request.mode not in MODES:
        raise ValueError("mode must be pr or conversation")
    if request.mode == PR_MODE:
        _validate_pr_request(request)
    else:
        _validate_conversation_request(request)


def _validate_pr_request(request):
    for field in ("proposal", "consequence", "recommendation", "question"):
        _require_non_empty_string(getattr(request, field), field)
    if request.receipts is not None:
        raise ValueError("pr mode receipts are fixed and cannot be overridden")
    if request.title or request.context is not None:
        raise ValueError("title and context are available only in conversation mode")
    if request.demo:
        return
    hexadecimal = set("0123456789abcdefABCDEF")
    revisions = (request.head_sha, request.base_sha)
    if any(
        not isinstance(revision, str)
        or len(revision) != 40
        or not set(revision) <= hexadecimal
        for revision in revisions
    ):
        raise ValueError("head and base revision must be 40 hexadecimal characters")
    if not isinstance(request.pr_number, int) or request.pr_number < 1:
        raise ValueError("pull request number must be positive")
    if not isinstance(request.repository, str) or request.repository.count("/") != 1:
        raise ValueError("repository must be owner/name")


def _validate_conversation_request(request):
    _require_non_empty_string(request.title, "title")
    _require_non_empty_string(request.question, "question")
    for field in ("proposal", "consequence", "recommendation"):
        if not isinstance(getattr(request, field), str):
            raise ValueError(f"{field} must be a string")
    if any(
        getattr(request, field) is not None
        for field in ("repository", "pr_number", "head_sha", "base_sha")
    ):
        raise ValueError("conversation mode PR fields must be absent")
    if request.receipts is not None:
        _validate_receipts(request.receipts)
    if request.context is not None:
        _validate_context(request.context)


def sanitize_request(request):
    if request.mode == PR_MODE:
        if not request.demo:
            return request
        return replace(
            request,
            repository="__demo__",
            pr_number=0,
            head_sha="0" * 40,
            base_sha="0" * 40,
        )
    return replace(
        request,
        receipts=[] if request.demo or request.receipts is None else request.receipts,
        context={} if request.demo or request.context is None else request.context,
    )


def storage_fields(request):
    if request.mode == PR_MODE:
        return {
            "repository": request.repository,
            "pr_number": request.pr_number,
            "head_sha": request.head_sha,
            "base_sha": request.base_sha,
            "mode": PR_MODE,
            "context": None,
        }
    context = canonical_json(
        {
            "context": request.context,
            "receipts": request.receipts,
            "title": request.title,
        }
    )
    return {
        "repository": "",
        "pr_number": 0,
        "head_sha": "",
        "base_sha": "",
        "mode": CONVERSATION_MODE,
        "context": context,
    }


def load_stored_mode(decision):
    mode = decision.get("mode")
    if mode == PR_MODE:
        if decision.get("context") is not None:
            raise ValueError("pr mode cannot contain conversation context")
        return StoredMode(PR_MODE, receipts=PR_RECEIPTS)
    if mode != CONVERSATION_MODE:
        raise ValueError("stored mode is unknown")
    raw_context = decision.get("context")
    if not isinstance(raw_context, str):
        raise ValueError("stored conversation context is missing")
    try:
        payload = json.loads(raw_context)
    except json.JSONDecodeError as error:
        raise ValueError("stored conversation context is malformed") from error
    if not isinstance(payload, dict) or set(payload) != {"title", "receipts", "context"}:
        raise ValueError("stored conversation context has an invalid shape")
    _require_non_empty_string(payload["title"], "stored title")
    if payload["receipts"]:
        _validate_receipts(payload["receipts"])
    elif payload["receipts"] != []:
        raise ValueError("stored receipts must be a list")
    _validate_context(payload["context"])
    if canonical_json(payload) != raw_context:
        raise ValueError("stored conversation context is not canonical")
    return StoredMode(
        CONVERSATION_MODE,
        title=payload["title"],
        receipts=frozenset(payload["receipts"]),
        context=payload["context"],
    )


def alert_body(request, digest):
    if request.mode == PR_MODE:
        return _pr_alert_body(request, digest)
    if request.demo:
        return (
            "DEMO CONVERSATION RELAY CHECK\n\n"
            f"Title: {request.title}\n"
            f"Question: {request.question}\n\n"
            "This demo accepts no decision words. Reply with a free-form question to test routing."
        )
    details = []
    for label, value in (
        ("Proposal", request.proposal),
        ("Consequence", request.consequence),
        ("Recommendation", request.recommendation),
    ):
        if value:
            details.append(f"{label}: {value}")
    if request.context:
        details.append("Context:")
        details.extend(f"- {key}: {value}" for key, value in sorted(request.context.items()))
    middle = "\n".join(details)
    if middle:
        middle += "\n"
    if request.receipts:
        instruction = (
            "Reply with exactly one whole message: "
            f"{', '.join(request.receipts)}.\n"
            "These are delivery receipts only; the Paseo owner must revalidate before action."
        )
    else:
        instruction = "Reply with a question; this thread accepts no decision words."
    return (
        "CONVERSATION REPLY REQUESTED\n"
        f"{request.title}\n\n"
        f"{middle}"
        f"Question: {request.question}\n"
        f"Thread digest: {digest}\n\n"
        f"{instruction}"
    )


def _pr_alert_body(request, digest):
    if request.demo:
        return (
            "DEMO REVIEW RELAY CHECK — no real pull request\n\n"
            f"Proposal: {request.proposal}\n"
            f"Consequence: {request.consequence}\n"
            f"Question: {request.question}\n\n"
            "This demo cannot accept approve, reject, or hold. Reply with a free-form question to test routing."
        )
    return (
        "HUMAN DECISION REQUIRED\n"
        f"{request.repository}#{request.pr_number}\n\n"
        f"Proposal: {request.proposal}\n"
        f"Consequence: {request.consequence}\n"
        f"Recommendation: {request.recommendation}\n"
        f"Question: {request.question}\n"
        f"Revision: head {request.head_sha}; base {request.base_sha}\n"
        f"Proposal digest: {digest}\n\n"
        "Reply with exactly one whole message: approve, reject, or hold.\n"
        "Anything else is forwarded as a question. Delivery never merges or approves automatically."
    )


def answer_body(decision, answer):
    stored_mode = load_stored_mode(decision)
    if stored_mode.name == PR_MODE:
        return (
            f"PR owner reply — {decision['repository']}#{decision['pr_number']}\n"
            f"Decision: {decision['decision_id']}\n"
            f"Revision: head {decision['head_sha']}; base {decision['base_sha']}\n\n"
            f"{answer}\n\n"
            "Reply to this message to keep the same owner and revision association."
        )
    return (
        f"Paseo owner reply — {stored_mode.title}\n"
        f"Thread: {decision['decision_id']}\n\n"
        f"{answer}\n\n"
        "Reply to this message to keep the same owner and thread association."
    )


def prompt_lines(decision, stored_mode):
    if stored_mode.name == PR_MODE:
        return (
            f"repository={decision['repository']}\n"
            f"pr={decision['pr_number']}\n"
            f"head={decision['head_sha']}\n"
            f"base={decision['base_sha']}\n"
        )
    return (
        f"title={canonical_json(stored_mode.title)}\n"
        f"context={canonical_json(stored_mode.context)}\n"
    )


async def receipt_matches_external_state(decision, stored_mode, github):
    if stored_mode.name == CONVERSATION_MODE:
        return True
    live = await github.read_pull_request(decision["repository"], decision["pr_number"])
    return (
        live.get("state") == "OPEN"
        and live.get("head_sha") == decision["head_sha"]
        and live.get("base_sha") == decision["base_sha"]
    )
