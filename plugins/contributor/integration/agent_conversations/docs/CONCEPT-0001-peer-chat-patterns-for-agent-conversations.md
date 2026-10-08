---
kind: concept
id: agent-conversations-CONCEPT-0001
status: accepted
depends_on: []
related:
  - "Corvin-Knowledge: ADR-2234 (agent-to-agent conversations, moderator model)"
  - "Corvin-Knowledge: ADR-2235 (four actors in the peer chat)"
  - "Corvin-Knowledge: CONCEPT-0097, CONCEPT-0098"
paths:
  - plugins/contributor/integration/agent_conversations/**
---

# CONCEPT-0001 — Peer-chat patterns for Agent Conversations

**Status:** Accepted (Phase 1 built 2026-10-08) · **Date:** 2026-10-08 · **Scope:** this plugin only (Plugin Exception Rule —
plugin-specific concepts and ADRs live in `docs/`, not in Corvin-Knowledge).

## 1. Problem

`/app/agent-conversations` is a static console panel: a form, a list and a read-only transcript.
The operator can start a conversation and *watch*; they cannot take part. The peer chat
(`PeerConversation.tsx`) is the opposite: a chat the operator lives in — bubbles with authorship,
an always-open composer, slash commands, attachments, a per-peer settings dialog.

Goal: Agent Conversations feels like the peer chat, the operator can join at any moment, and the
settings are better than "turns + who speaks first". It ships as a Marketplace plugin, so the
panel (and its sidebar entry) exists only while the plugin is installed and enabled — same
pattern as `corvin_knowledge` and `video_producer`.

## 2. Conceptual level — what carries over from the peer chat, and what must not

| Peer-chat pattern | Carries over as | Deliberately different |
|---|---|---|
| The operator is a participant, not a viewer | The composer is **always** enabled — while a conversation runs and after it ended | A peer-chat message wakes the other side at once. Here the *moderator* owns the turn order, so an operator message is queued for the next turn boundary (an **interjection**), never injected mid-turn |
| Authorship is derived, never guessed (ADR-2235 four actors) | Four speakers: operator · your agent · peer agent · system (pause, resume, end) | System events are their own row type, not chat bubbles |
| Tucked-corner bubbles, right = mine | Right: operator + your agent. Left: peer agent. Centre: system rows | — |
| Slash palette | `/pause` `/resume` `/stop` `/next local\|peer` `/turns +N` `/topic …` | Parsed **server-side**, fail-closed (an unknown `/…` is an error, never sent as text — the lesson from ADR-2235) |
| Per-peer settings dialog (`PeerManagementDialog`) | A settings drawer per conversation + plugin-wide defaults | Not a permission dialog: the peer's executor right is still owned by the peer dialog |

**Invariant that must survive the adaptation:** the transcript has exactly **one writer** — the
moderator thread (`conversation.py`, ADR-2234). Every operator action (post, pause, next, resume)
is a *request* the moderator drains at a turn boundary and then writes. No second writer, no
race on `seq`.

## 3. Structural level

```
Plugin (Marketplace)                         CorvinOS core (unchanged contracts)
─────────────────────                        ───────────────────────────────────
plugin.yaml  console_panel ─────────────►   PluginPanelRegistry → manifest → sidebar (Marketplace)
src/*.py     settings model, command        thin route  /v1/console/plugins/agent-conversations/*
             parser, defaults                   │
                                                ▼
                                          core/federation/conversation.py   (moderator, transcript)
                                          + `mailbox` (operator requests)   ← the only core change
```

* **Panel** — `AgentConversationsPage` becomes a plugin panel: removed from `PANELS`/`NAV_GROUPS`,
  resolved through `COMPONENTS_BY_NAME`. Disabled plugin ⇒ no route, no sidebar entry.
* **Layout** — three columns like the chat: list (search, status filter, unread dot) · thread ·
  context drawer (participants, live status, settings). The *new conversation* form moves into a
  dialog so the thread owns the screen.
* **Backend ownership** — the settings model, command grammar and validation live in the plugin
  (`src/`), loaded by path exactly like `video_producer_api.py`. The mailbox lives in core because
  the moderator does; it is a small, generic *operator request queue*, not plugin logic.
* **Audit** — metadata only, never text (GDPR Art. 5, same as ADR-2234):
  `federation.conversation_operator_message` (ids, target, chars), `…_paused`, `…_resumed`.
  Registered in `EVENT_SEVERITY` **and** `_EVENT_ALLOWLIST` in the same commit as the emitter.

## 4. The "edit window" — how the operator takes part

One composer, three kinds of input, no modes to learn:

1. **Interjection (default).** Plain text. Delivered before the next turn to *both* agents as
   `Operator: …` inside the prompt. Targeted form: `@mine …` / `@peer …` — the other agent sees it
   only as "the operator spoke to <agent>".
2. **Steering.** Slash commands (above). `/next peer` overrides the speaker for one turn;
   `/turns +3` extends the budget; `/pause` finishes the current turn, then waits.
3. **Draft review (Phase 2).** Setting *Review my agent's turns*: the local agent's reply is held
   as a **draft inside the composer**. The operator edits it (that is the shared editing window),
   then *Send* releases it, *Regenerate* asks the agent again, *Discard* skips the turn. The peer's
   turns can never be edited — only the operator's own side is.

A finished conversation can be **continued** (`Continue +N turns`): a new moderator thread appends to
the same transcript. `end` records stay in the file; the status is derived from the last record.

## 5. Settings — better than "turns + first speaker"

Two scopes. Plugin-wide *defaults* in `plugin.yaml → settings_schema`; per-conversation values
chosen at start and editable while it runs (only fields marked live):

| Setting | Scope | Live? | Notes |
|---|---|---|---|
| Max turns | conversation | yes (`/turns`) | cap stays `MAX_TURNS_CAP` = 12 (core) |
| First speaker | conversation | no | |
| Turn length (≈ words) | both | yes | replaces the hard-coded "about 250 words" |
| Agent role notes (per agent) | conversation | no | ≤ 500 chars, framed as operator instruction |
| Pacing: pause between turns (0–60 s) | both | yes | gives the operator a window to interject |
| Control mode: `auto` / `review` | both | yes | review = draft window (Phase 2) |
| Stop when agents agree | conversation | yes | agent ends its turn with a fixed marker line; moderator ends the conversation |
| Keep finished conversations | plugin | — | feeds the existing 50-per-tenant cap |

Peer-side permissions (observer/executor, `spawn_worker`, `federable`) are **not** duplicated here:
the drawer links to the existing peer dialog. One flag, one owner.

## 6. Implementation level — phases

| Phase | Delivers | Proof |
|---|---|---|
| 1 | Plugin skeleton (`plugin.json`/`yaml`/`provider.py`), panel moved to plugin, peer-chat layout and bubbles, composer with interjection + pause/resume/stop, settings (turns, length, pacing, role notes), mailbox in `conversation.py` | pytest through the real router; Playwright against the live console |
| 2 | Draft review window, `/next`, `/turns`, continue-after-end, agreement stop | same |
| 3 | Attachments in interjections, unread markers, export transcript | same |

## 7. Alternatives considered

* **Embed agent conversations into the peer chat** — rejected: ADR-2235 already routes `/ask` and
  `/talk` there; a separate, moderated, multi-turn surface needs its own list and lifecycle.
* **Let the operator write straight into the transcript file** — rejected: second writer, breaks
  `seq` monotonicity and the "one writer" invariant that makes the file trustworthy.
* **Websocket instead of polling** — deferred: the 1 s poll already matches the peer chat's feed
  transport; revisit only if turn latency, not transport, becomes the problem.

## 8. When NOT to use this pattern

Where the peer is a human, use the plain peer chat. The moderator/mailbox model exists because
*agents* take turns on a budget; a human peer has no budget to moderate.

## Status notes

* **2026-10-08 — Phase 1 built; deviations from the text above.**
  * Routes: no new `/plugins/agent-conversations/*` module — the existing
    `/v1/console/federation/conversations*` routes were extended (one owner for the moderator's API).
  * Validation and the slash grammar live in **core** (`normalize_settings`, `COMMANDS`), not in plugin
    `src/` — see ADR-0001 point 3. The plugin owns UI, manifest and docs; `src/` is not needed.
  * Role notes are live-editable (the concept marked them fixed); the backend applies them from the
    next turn at no extra cost.
  * After a conversation ends the composer is **disabled** (Phase 2 delivers *Continue +N turns*).
  * Shipped slash commands: `/pause /resume /stop /words N /pace N`. `/next`, `/turns`, `/topic` are Phase 2.
  * The "Stop when agents agree" setting and the draft-review window are Phase 2.

## Operator Notes
_(append-only, timestamped, human-authored)_
