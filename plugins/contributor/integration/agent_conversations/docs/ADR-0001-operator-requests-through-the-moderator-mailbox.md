---
id: agent-conversations-ADR-0001
status: accepted
depends_on: []
related:
  - "Corvin-Knowledge: ADR-2234 (moderated agent-to-agent conversations)"
  - agent-conversations-CONCEPT-0001
paths:
  - "CorvinOS: core/federation/conversation.py"
  - "CorvinOS: core/console/corvin_console/routes/federation_routes.py"
  - "CorvinOS: core/federation/audit.py"
docs:
  - "CorvinOS: docs/claude-ref/layer-plugins.md § Agent Conversations"
---

# ADR-0001 — Operator input reaches a conversation only through the moderator's mailbox

**Status:** Accepted · **Date:** 2026-10-08

## Context
*Conceptual:* the operator is a participant of an agent conversation, not a viewer — but the
conversation is *moderated*: the moderator owns turn order and the transcript (ADR-2234).
*Structural:* the transcript file is append-only with strictly increasing `seq` and exactly one
writer; that is what makes it a trustworthy record. A second writer (a request handler appending an
operator line) would race on `seq`.
*Implementation:* the moderator is a daemon thread; handlers run on the event loop's executor.

## Decision
1. Every operator action is a **request** in an in-memory queue (`_REQUESTS`, guarded by `_LIVE_LOCK`,
   ≤ 5 pending). Only the moderator drains it — before each turn and during the pacing/pause wait —
   and writes the records. Handlers never touch the file.
2. Pause, resume and settings changes are written as `kind: "event"` records so the transcript tells
   the whole story; `GET` returns them as `events`, separate from `messages` (older readers keep working).
3. Settings validation and the slash grammar live in core (`normalize_settings`, `COMMANDS`,
   `run_command`), not in the plugin or client: validation must hold for any caller, and a client copy
   of a grammar drifts (ADR-2235).
4. A request that arrives after the last turn is written by the final drain, unanswered — never dropped.
5. Audit stays metadata-only (ids, target, char counts) and is written **before** the record, so an
   unrecorded interjection is never shown (audit-first, as in ADR-2234).

## Alternatives considered
* *Handler appends to the file under a file lock* — rejected: two writers, ordering by lock luck,
  and a transcript erased mid-run could be re-created.
* *Interrupt the running turn to deliver the message* — rejected: a turn may be a signed delegation
  to a peer; cancelling it half-way has no defined meaning on the wire.

## Consequences
* An interjection lands at the next turn boundary, not instantly; the *pause between turns* setting
  exists to give the operator a window.
* The plugin owns UI and docs; the moderator stays core. Disabling the plugin hides the panel, it
  does not change what the moderator accepts.
* Not yet built (concept §6, Phase 2): editable draft of your agent's turn, `/next`, `/turns`,
  continue-after-end, agreement stop.
