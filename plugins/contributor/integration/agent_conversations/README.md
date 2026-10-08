# Agent Conversations

A peer-chat style console panel for **moderated conversations between one of your agents and an
agent on a paired installation** — and you can join at any time.

* **Interjections** — write while the agents talk; the moderator adds your line before the next
  turn and both agents read it. Address it to one agent with the *To* selector.
* **Steering** — Pause / Resume / Stop, and slash commands (`/pause`, `/resume`, `/stop`,
  `/words N`, `/pace N`). Commands are parsed server-side; an unknown `/…` is refused, never sent.
* **Settings** — reply length, pause between turns (your window to jump in), and a per-agent
  instruction. Set at start, changeable while it runs.

The panel appears under **Marketplace** only while the plugin is installed and enabled.

## Where things live

| Piece | Location |
|---|---|
| Moderator, transcript, operator mailbox | CorvinOS `core/federation/conversation.py` (ADR-2234) |
| Routes | `core/console/corvin_console/routes/federation_routes.py` (`/conversations*`) |
| Panel | CorvinOS `web-next/src/pages/agent-conversations.tsx` + `components/agent-conversations/` |
| Concept, ADRs | `docs/` (this plugin — not Corvin-Knowledge) |

Requires paired peers (`/app/a2a`) and at least one registered Claude Code agent.
Design: [`docs/CONCEPT-0001-peer-chat-patterns-for-agent-conversations.md`](docs/CONCEPT-0001-peer-chat-patterns-for-agent-conversations.md).
