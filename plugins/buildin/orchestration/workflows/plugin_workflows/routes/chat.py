"""WebSocket design chat route — guided workflow assistant (Phase 7)."""
import asyncio
import json
import logging
import subprocess
import sys
import time
from typing import Any, AsyncIterator

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .helpers import (
    validate_wid, require_workflow, write_atomic, append_chat_line_async,
    chat_path, meta_path, read_json_or_none, WorkflowLockBusy,
)

_log = logging.getLogger(__name__)

router = APIRouter()


# ── Dependency injection (soft dep) ────────────────────────────────────

class ChatAdapter:
    """Adapter for chat dependencies."""

    def __init__(self, forge_paths, prompt_guard=None, spawn_gates=None):
        self.forge_paths = forge_paths
        self.prompt_guard = prompt_guard  # Soft dep: fail-closed if None
        self.spawn_gates = spawn_gates  # Soft dep: spawn gate checks


def get_chat_adapter() -> ChatAdapter:
    """Inject dependencies (override in plugin bootstrap)."""
    raise NotImplementedError("chat adapter not initialized in plugin bootstrap")


# ── Prompt guard (shared with workflows.py, fail-closed) ────────────────

def _guard_prompt_head(text: str) -> str:
    """Guard workflow prompts against shell expansions before claude -p spawn.

    Fail-closed: if guard is unavailable, raises RuntimeError instead of
    passing unguarded payload.
    """
    try:
        from prompt_guard import guard_prompt_head
        return guard_prompt_head(text)
    except ImportError:
        raise RuntimeError(
            "shared claude-CLI prompt guard unavailable "
            "(prompt_guard.py not found) - refusing to spawn unguarded"
        )


# ── Workflow design templates ──────────────────────────────────────────

_TEMPLATES: dict[str, dict[str, Any]] = {
    "daily-digest": {
        "keywords": ["daily", "digest", "rss", "feed", "morning", "news", "summary"],
        "steps": "TRIGGER > fetch_content > summarise > deliver",
        "yaml": (
            'awp: "1.0.0"\n'
            'workflow:\n'
            '  name: daily_digest\n'
            '  description: "Fetch and summarise content, then deliver a digest."\n'
            'orchestration:\n'
            '  engine: dag\n'
            '  graph:\n'
            '    - id: fetch_content\n'
            '      type: agent\n'
            '      agent: assistant\n'
            '      instructions: "Fetch news from Hacker News and summarise top 5 stories."\n'
            '      forge_tools: [http.get]\n'
            '    - id: deliver\n'
            '      type: deliver\n'
            '      depends_on: [fetch_content]\n'
            '      config:\n'
            '        channel: discord\n'
        ),
    },
    "content-moderation": {
        "keywords": ["moderation", "content", "filter", "safety", "detect"],
        "steps": "TRIGGER > classify > filter > log",
        "yaml": (
            'awp: "1.0.0"\n'
            'workflow:\n'
            '  name: content_moderation\n'
            '  description: "Classify and filter user-generated content."\n'
            'orchestration:\n'
            '  engine: dag\n'
            '  graph:\n'
            '    - id: classify\n'
            '      type: agent\n'
            '      agent: assistant\n'
            '      instructions: "Classify content by safety category."\n'
        ),
    },
}


def _suggest_template(query: str) -> str | None:
    """Suggest a workflow template based on keywords (best-effort)."""
    query_lower = query.lower()
    for template_name, template in _TEMPLATES.items():
        keywords = template.get("keywords", [])
        if any(kw in query_lower for kw in keywords):
            return template_name
    return None


# ── Routes: Chat ───────────────────────────────────────────────────────

@router.websocket("/workflows/{wid}/chat")
async def workflow_design_chat(
    websocket: WebSocket,
    wid: str,
    tenant_id: str,
    adapter: ChatAdapter,
):
    """WebSocket design assistant for workflow creation and refinement.

    Phase 7 feature: real-time collaborative workflow design via Claude CLI.
    Supports chat history persistence, template suggestions, and LLM-guided
    workflow building via YAML generation.
    """
    validate_wid(wid)

    try:
        meta = require_workflow(tenant_id, wid, adapter.forge_paths)
    except Exception:
        await websocket.close(code=4004, reason="workflow not found")
        return

    await websocket.accept()
    chat_p = chat_path(tenant_id, wid, adapter.forge_paths)

    try:
        # Read existing chat history
        chat_history: list[dict[str, Any]] = []
        if chat_p.exists():
            for line in chat_p.read_text(encoding="utf-8").splitlines():
                try:
                    chat_history.append(json.loads(line))
                except Exception:
                    pass

        # Send history on connect
        await websocket.send_json({
            "type": "history",
            "messages": chat_history[-50:],  # Last 50 messages
        })

        # Chat loop
        while True:
            try:
                # Receive message
                data = await websocket.receive_json()
                role = data.get("role", "user")
                content = data.get("content", "").strip()

                if not content:
                    continue

                # Append to chat history
                user_msg = {
                    "role": role,
                    "content": content[:4000],  # Bounded
                    "timestamp": time.time(),
                }
                chat_history.append(user_msg)

                # Persist message (async, bounded)
                try:
                    ok = await append_chat_line_async(tenant_id, wid, user_msg, adapter.forge_paths)
                    if not ok:
                        await websocket.send_json({
                            "type": "error",
                            "message": "chat append lock busy — retry",
                        })
                        chat_history.pop()  # Don't keep failed append
                        continue
                except WorkflowLockBusy:
                    await websocket.send_json({
                        "type": "error",
                        "message": "chat append lock busy — retry",
                    })
                    chat_history.pop()
                    continue

                # Generate assistant response via Claude CLI
                try:
                    # Guard prompt fail-closed
                    guarded_content = _guard_prompt_head(content)
                except RuntimeError as exc:
                    await websocket.send_json({
                        "type": "error",
                        "message": f"prompt guard failed: {exc}",
                    })
                    continue

                # Check spawn gates (L44, soft dep)
                if adapter.spawn_gates:
                    refusal = adapter.spawn_gates.check_console_spawn_or_refusal(
                        guarded_content,
                        tenant_id=tenant_id,
                        persona="assistant",
                        channel="workflow-chat",
                        chat_key=f"workflow-chat:{wid}",
                        engine_id="claude_code",
                    )
                    if refusal:
                        await websocket.send_json({
                            "type": "error",
                            "message": refusal,
                        })
                        continue

                # Invoke Claude CLI (async, subprocess)
                def _run_claude():
                    try:
                        result = subprocess.run(
                            ["claude", "-p", "--max-tokens", "1000", "--output-format", "text"],
                            input=guarded_content,
                            capture_output=True,
                            text=True,
                            timeout=30,
                        )
                        if result.returncode == 0:
                            return result.stdout.strip()
                        return f"[error rc={result.returncode}] {result.stderr.strip()[:200]}"
                    except FileNotFoundError:
                        return "[claude CLI not found]"
                    except subprocess.TimeoutExpired:
                        return "[timeout after 30s]"
                    except Exception as exc:
                        return f"[exception: {exc}]"

                assistant_response = await asyncio.to_thread(lambda: _run_claude())

                # Check for template suggestions
                template_name = _suggest_template(content)
                template_suggestion = None
                if template_name and template_name in _TEMPLATES:
                    template_suggestion = {
                        "name": template_name,
                        "steps": _TEMPLATES[template_name]["steps"],
                        "yaml_sample": _TEMPLATES[template_name]["yaml"],
                    }

                # Append assistant message to history
                assistant_msg = {
                    "role": "assistant",
                    "content": assistant_response,
                    "template_suggestion": template_suggestion,
                    "timestamp": time.time(),
                }
                chat_history.append(assistant_msg)

                # Persist assistant message
                try:
                    await append_chat_line_async(tenant_id, wid, assistant_msg, adapter.forge_paths)
                except Exception:
                    pass  # Non-fatal: message was generated but not persisted

                # Send response
                await websocket.send_json({
                    "type": "message",
                    "role": "assistant",
                    "content": assistant_response,
                    "template_suggestion": template_suggestion,
                })

            except WebSocketDisconnect:
                break
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "invalid JSON"})
            except Exception as exc:
                _log.error("workflow chat error: %s", exc, exc_info=True)
                await websocket.send_json({
                    "type": "error",
                    "message": f"unexpected error: {exc}",
                })

    except Exception as exc:
        _log.error("workflow chat WebSocket error: %s", exc, exc_info=True)
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


# ── Helper for appending to chat JSONL (async) ────────────────────────

async def append_chat_line_async(
    tenant_id: str,
    wid: str,
    line: dict[str, Any],
    forge_paths,
) -> bool:
    """Persist a chat line from the async WS handler without stalling the loop.

    Returns True when the line was persisted, False when the append
    lock was busy at the deadline.
    """
    from .helpers import append_chat_line as sync_append

    def _write() -> bool:
        try:
            sync_append(tenant_id, wid, line, forge_paths)
            return True
        except WorkflowLockBusy:
            return False

    return await asyncio.to_thread(lambda: _write())
