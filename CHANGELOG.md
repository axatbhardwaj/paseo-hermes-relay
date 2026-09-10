# Changelog

## 0.2.0 - 2026-09-11

- Add generic `conversation` threads with required title/question, optional
  prose, zero-to-five opt-in receipt words, and a 2048-byte canonical JSON
  context limit.
- Keep absent `mode` equivalent to `pr`, including the fixed PR receipt words
  and exact live state/head/base validation.
- Migrate SQLite additively and transactionally while preserving existing PR
  decisions, digests, attempts, and anchors; mode and context are immutable.
- Fail closed on unknown stored modes or malformed stored context, and keep all
  sender, owner, server, duplicate, status, unsafe-message, and uncertain-send
  protections.
- Clarify that receipts prove delivery only and never grant action authority.
- Retain the `paseo-review-relay` plugin key and data path for live routing
  compatibility. Conversation threads must be reconciled and closed before
  downgrading to 0.1.

## 0.1.0 - 2026-09-11

- Extract the reviewed `paseo-review-relay` Hermes plugin and its history.
- Preserve the ten runtime, CLI, config, and manifest files from Haoshoku
  `3c792cb` byte-for-byte.
- Import the 54-test standard-library suite for standalone execution.
- Document pinned installation, private configuration, reply handling, and the
  accepted relay specification.
- Require a symlink for the `hermes-relay` wrapper so relative imports resolve
  from the plugin checkout.
