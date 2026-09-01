# Bridge Adapters

A **bridge adapter** adds a new messaging channel (Matrix, Signal, Teams, IRC, a
custom webhook — anything) to CorvinOS. A bridge is a pair: a **Node.js daemon** that
speaks the channel's protocol, and a **`settings.json`** the shared adapter reads to
configure routing. Adding a channel means writing one daemon file and one settings
file — **no changes** to the shared adapter or any other part of CorvinOS.

## Minimum requirements

A bridge daemon must:

1. Accept messages from the channel and write them to the shared inbox.
2. Accept reply envelopes from the inbox and send them back to the channel.
3. Expose `GET /status` on its assigned port returning `{"status": "ok"}`.
4. Ship a `settings.json` with at least `whitelist` (array) + a token field (optionally `chat_profiles`, `rate_limit_per_hour`).
5. Ship an `install.sh` that runs `npm install`.
6. Register a block in `operator/bridges/bridge.sh` so `up/down/status/tail` work uniformly.

## Inbox protocol

Incoming (daemon → adapter):

```json
{ "channel": "mybridge", "chat_key": "mybridge:12345", "user_id": "12345", "text": "Hello", "attachments": [], "ts": 1716288000.0 }
```

Outgoing (adapter → daemon):

```json
{ "chat_key": "mybridge:12345", "text": "Hello back", "audio_path": "/tmp/corvin/tts_12345.ogg", "is_voice": true }
```

## Hot-reload boundary

Read `settings.json` on **every** message (not once at boot) via `currentSettings()`
from `operator/bridges/shared/js/settings.js` — this gives hot-reload for whitelist,
pins, rate-limit, and chat-profile changes.

| Change | Restart? |
|---|---|
| `whitelist`, `rate_limit_per_hour`, `chat_profiles` | ❌ hot-reloaded |
| Daemon JavaScript code | ✅ `bridge.sh restart <channel>` |
| Bot token / webhook URL / port | ✅ `bridge.sh restart <channel>` |

## Reference implementation

The **Telegram daemon** (`operator/bridges/telegram/daemon.js`, ~400 lines) is the
cleanest complete template: bot init, whitelist, rate limiting, the inbox protocol,
media handling, command passthrough, graceful shutdown.

## Canonical docs

- **[extending.md §4 — Bridge Adapters](https://github.com/CorvinLabs/CorvinOS/blob/main/docs/extending.md)**
- **[bridge-setup.md](https://github.com/CorvinLabs/CorvinOS/blob/main/docs/bridge-setup.md)** — running and configuring bridges

## Contributing to the marketplace

Add `bridge-adapters/<channel>/` with `daemon.js`, `settings.example.json`,
`install.sh`, and a `README.md` (setup steps, required tokens/scopes). See
[CONTRIBUTING.md](../CONTRIBUTING.md).
