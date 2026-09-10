# Generic Paseo conversation relay

> Accepted for standalone relay 0.2.0. Astra: AGREE. Fable: AGREE.
> Decision category: context and decision-receipt boundary.

The relay carries anchored Telegram replies to the exact persistent Paseo
conversation owner that opened a thread. Pull-request review is one supported
use case, not the relay's identity. The relay is a transport boundary: it never
approves, merges, deploys, chooses another owner, or expands prior authority.

The first deployment continues to use the legacy Hermes plugin key and data
path `paseo-review-relay`. Renaming either would orphan live configuration,
SQLite state, and reply anchors, so naming migration is outside 0.2.0.

## Modes

Each immutable thread has one explicit mode:

- `pr` is the default when `mode` is absent. It preserves the 0.1 request
  shape, PR alert and answer wording, fixed `approve`, `reject`, and `hold`
  receipts, and the live GitHub state/head/base check before a receipt is
  forwarded.
- `conversation` requires `title` and `question` and rejects PR fields. It can
  carry optional `proposal`, `consequence`, `recommendation`, a bounded context
  map, and zero to five unique opt-in receipt words. It never invokes GitHub.

Conversation receipts default to none. Configured receipts are unique lowercase
ASCII single words and are delivery receipts for the exact immutable thread
only. An explicit empty receipt list is non-authorizing and equivalent to
omission.
Every forwarded receipt says `driver_must_revalidate=true`; the persistent
owner remains responsible for authority, context, and current-state validation
before acting. Questions never authorize action.

`context` is a JSON object whose keys and values are strings. Its canonical
UTF-8 JSON encoding is limited to 2048 bytes. It is included in the digest and
forwarding prompt. Telegram alerts JSON-escape each context key and value so
context cannot add instruction lines. Unknown request modes, unknown stored
modes, and malformed stored conversation context fail closed.

## Conversation request

```json
{
  "decision_id": "deploy-window-2026-09-12",
  "owner_agent_id": "PERSISTENT_PASEO_AGENT_ID",
  "server_id": "LOCAL_PASEO_SERVER_ID",
  "mode": "conversation",
  "title": "Production deploy window",
  "question": "Deploy the queue fix tonight at 22:00 IST?",
  "proposal": "Deploy the reviewed queue fix",
  "consequence": "Workers restart once",
  "recommendation": "Use the low-traffic window",
  "receipts": ["approve", "reject", "hold"],
  "context": {
    "runbook": "deploy.md",
    "ticket": "ENG-142"
  },
  "demo": false
}
```

Required common fields are `decision_id`, `owner_agent_id`, and `server_id`.
Conversation mode additionally requires `title` and `question`. Its three prose
detail fields are optional strings. `repository`, `pr_number`, `head_sha`, and
`base_sha` must be absent.

PR mode retains the 0.1 requirements verbatim: repository in `owner/name`
form, positive PR number, exact 40-hex head and base revisions, and non-empty
proposal, consequence, recommendation, and question. PR receipt words cannot
be overridden. Demo requests remain routing-only and cannot accept receipts;
conversation demos also remove context before persistence and delivery.

## User flow

1. A persistent Paseo owner opens a thread with an immutable ID, server, mode,
   content digest, and mode-specific context. The resulting Telegram message
   becomes a reply anchor.
2. A reply to that alert is admitted only from the configured Telegram user in
   the configured direct-message chat. Hermes forwards the exact text to that
   exact persistent owner.
3. The owner can publish an answer through the relay. The confirmed answer
   message becomes another anchor for the same thread.
4. A whole-message receipt is recognized only when configured by the thread's
   mode. Other eligible text is a question.
5. Material changes use `supersede`; they never mutate an existing identity.
   Closed, superseded, blocked, uncertain, missing-owner, and archived-owner
   replies receive an explanation rather than being guessed or replayed.

## Runtime boundary

The user plugin at `~/.hermes/plugins/paseo-review-relay` registers only
`pre_gateway_dispatch`. The inline hook admits only Telegram DM events whose
configured chat and sender match and whose reply message ID is in plugin state.
Forwarded messages, edited messages, bot messages, attachments, and mapped
messages from unauthorized senders never reach Paseo. Unrelated messages
continue through normal Hermes dispatch.

The hook performs no network or process work inline. It persists an event once
and uses `ctx.spawn_task` for asynchronous processing. External commands use
fixed argument arrays and private UTF-8 prompt files; user text is never
interpolated into a shell command.

Before every forward, the relay inspects the exact local Paseo owner and server
identity and rejects missing, archived, or mismatched owners. PR receipts then
read live GitHub PR state/head/base through fixed `gh` arguments. Any mismatch
or read failure blocks forwarding. A mismatch blocks the thread; a read failure
leaves the receipt failed and retryable without changing the open thread.
Conversation receipts perform no external domain check and therefore retain the
explicit driver revalidation marker. The decision row is re-read after
asynchronous checks before delivery, closing all but the final external-state
race.

## Storage and migration

SQLite transport state remains under
`~/.hermes/plugin-data/paseo-review-relay`. Version 0.2 adds `mode TEXT NOT NULL
DEFAULT 'pr'` and nullable `context TEXT` to `decisions` in one transaction and
recreates the identity trigger in that transaction to cover both columns.
Existing rows therefore become PR rows without changing their IDs, owners,
servers, PR revisions, digests, statuses, attempts, or anchors.

Conversation rows use neutral sentinel values only in the legacy non-null PR
columns; generic request files and messages never contain dummy PR data. Their
`context` column holds canonical JSON containing the title, receipt list, and
bounded context map. Mode and stored context are immutable.

Ensure the decision record exists and create the outbound-attempt record before
sending every alert or owner answer. Attach the returned message ID as a reply
anchor only after the external platform confirms delivery.

The proposal digest covers the canonical 0.2 request after demo sanitization,
including mode, title, receipts, and context. Existing stored 0.1 digests are
preserved. Newly opened 0.2 requests are not promised to reproduce a 0.1
digest; changing a request uses `supersede`, never a row update.

Inbound receipts are forwarded at most once. An ambiguous external send is
recorded as uncertain and never automatically replayed after restart. Definite
send failures remain visible and can be retried explicitly.

## Upgrade and rollback

Do not open conversation-mode threads until the 0.2 plugin activation and
native Hermes discovery checks have succeeded. Before upgrade, quiesce the
gateway and back up the complete plugin-data directory, including SQLite WAL
files. Upgrade preserves the existing live PR decision and all reply anchors.

Version 0.1 does not understand conversation rows. Before downgrading, reconcile
and close every conversation thread, retain a complete database backup, and
verify the remaining PR transport state. Never run old and new code against the
same live database concurrently, blindly restore an older database, or delete
the current database to force compatibility.

## Acceptance

- A generic alert contains title, context, and question without repository,
  PR number, Git revision, dummy PR, or GitHub installation requirements.
- Its reply reaches exactly its persistent Paseo owner, and an owner answer is
  replyable again without PR wording.
- Existing PR records and legacy requests retain owner binding and exact live
  state/head/base guards. A missing mode migrates to `pr`; an unknown mode
  cannot downgrade a PR record to a generic thread.
- Wrong sender/chat/platform, unsafe input, unknown anchor, duplicate input,
  closed or superseded state, archived owner, stale revision, server mismatch,
  and ambiguous delivery retain their protections.
- Migration from the actual 0.1 schema preserves a decision, three anchors, and
  its digest while making mode and context immutable.
- Python 3.11 and the local interpreter pass the full dependency-free suite and
  compilation checks.
- A clearly labeled demo alert reaches Telegram; a real user reply is the final
  end-to-end check. Do not fabricate a user event as proof of phone interaction.

Delivery success means the external platform returned a message ID. It does not
prove the user read the message, and a receipt does not grant action authority.
