"""Shared workflow route helpers — path resolution, file I/O, locking."""
import aiofiles
import fcntl
import json
import os
import re
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status as http_status


# ── Constants ──────────────────────────────────────────────────────────

_WID_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_RID_BYTES = 8
LOCK_TIMEOUT_SECONDS = 2.0
LOCK_RETRY_INTERVAL_SECONDS = 0.01


# ── Exceptions ─────────────────────────────────────────────────────────

class WorkflowLockBusy(TimeoutError):
    """A workflow file lock stayed held past LOCK_TIMEOUT_SECONDS.

    A TimeoutError (hence an OSError), matching
    core.infinite_session.event_store.SnapshotLockBusy, so callers
    that already degrade on I/O failure keep degrading instead of raising.
    """


# ── Path resolution ────────────────────────────────────────────────────

def workflows_dir(tenant_id: str, forge_paths) -> Path:
    """Tenant workflows directory root."""
    return forge_paths.tenant_home(tenant_id) / "workflows"


def yaml_path(tenant_id: str, wid: str, forge_paths) -> Path:
    """Path to workflow YAML file."""
    return workflows_dir(tenant_id, forge_paths) / f"{wid}.awp.yaml"


def meta_path(tenant_id: str, wid: str, forge_paths) -> Path:
    """Path to workflow metadata JSON file."""
    return workflows_dir(tenant_id, forge_paths) / f"{wid}.meta.json"


def chat_path(tenant_id: str, wid: str, forge_paths) -> Path:
    """Path to workflow design chat JSONL file."""
    return workflows_dir(tenant_id, forge_paths) / f"{wid}.chat.jsonl"


def runs_dir(tenant_id: str, wid: str, forge_paths) -> Path:
    """Path to workflow runs directory."""
    return workflows_dir(tenant_id, forge_paths) / wid / "runs"


def run_meta_path(tenant_id: str, wid: str, rid: str, forge_paths) -> Path:
    """Path to run metadata JSON file."""
    return runs_dir(tenant_id, wid, forge_paths) / f"{rid}.meta.json"


def run_log_path(tenant_id: str, wid: str, rid: str, forge_paths) -> Path:
    """Path to run event log JSONL file."""
    return runs_dir(tenant_id, wid, forge_paths) / f"{rid}.jsonl"


def approval_path(tenant_id: str, wid: str, rid: str, forge_paths) -> Path:
    """Path to run approval gate JSON file."""
    return runs_dir(tenant_id, wid, forge_paths) / f"{rid}.approval.json"


# ── File I/O ───────────────────────────────────────────────────────────

def ensure_dir(path: Path) -> None:
    """Create directory and parents if needed."""
    path.mkdir(parents=True, exist_ok=True)


def write_atomic(path: Path, data: dict[str, Any] | str, mode: int = 0o600) -> None:
    """Write file atomically with secure permissions (TOCTOU-safe, fail-closed).

    Args:
        path: Target file path
        data: Content to write (dict → JSON, str → verbatim)
        mode: File permissions (default 0o600 = owner rw only, ADR-0232)

    Guarantees:
        - Atomic write (via temp + os.replace)
        - TOCTOU-safe (temp file created with O_CREAT | O_EXCL)
        - Secure permissions (0o600 default, fail-closed if umask interferes)
        - Synced to disk (os.fsync)
    """
    ensure_dir(path.parent)
    raw = (data if isinstance(data, str) else json.dumps(data, indent=2, ensure_ascii=False)) + "\n"

    # Open temp file with O_CREAT | O_EXCL for TOCTOU safety + secure mode
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    try:
        # Set mode on the file descriptor (before writing)
        os.chmod(fd, mode)

        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(raw)
            fh.flush()
            os.fsync(fh.fileno())

        # Atomic rename
        os.replace(tmp, path)

        # Verify final permissions (fail-closed)
        actual_mode = os.stat(path).st_mode & 0o777
        if actual_mode != mode:
            # Umask interfered — try to fix
            os.chmod(path, mode)
            actual_mode = os.stat(path).st_mode & 0o777
            if actual_mode != mode:
                raise OSError(f"Failed to set file permissions: {oct(actual_mode)} != {oct(mode)}")

    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def read_json_or_none(path: Path) -> dict[str, Any] | None:
    """Read JSON file, return None on missing or parse error."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


# ── File locking (bounded, fail-closed) ────────────────────────────────

@contextmanager
def bounded_flock(lock_path: Path, what: str, *, timeout: float | None = None):
    """Exclusive advisory lock with hard deadline (never blocks forever).

    Raises WorkflowLockBusy at the deadline instead of waiting.
    Used for workflow creation and chat append operations to prevent
    infinite hangs on wedged file handles.
    """
    limit = LOCK_TIMEOUT_SECONDS if timeout is None else timeout
    ensure_dir(lock_path.parent)
    with open(lock_path, "a") as lock_fh:
        deadline = time.monotonic() + limit
        while True:
            try:
                fcntl.flock(lock_fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise WorkflowLockBusy(
                        f"{what} lock busy: still held after {limit:g}s — "
                        f"refusing to block the caller"
                    ) from None
                time.sleep(LOCK_RETRY_INTERVAL_SECONDS)
        try:
            yield
        finally:
            fcntl.flock(lock_fh.fileno(), fcntl.LOCK_UN)


# ── Validation ─────────────────────────────────────────────────────────

def validate_wid(wid: str) -> str:
    """Validate workflow ID format (fail-closed)."""
    if not _WID_RE.match(wid):
        raise HTTPException(http_status.HTTP_400_BAD_REQUEST, f"invalid workflow id: {wid!r}")
    return wid


def require_workflow(tenant_id: str, wid: str, forge_paths) -> dict[str, Any]:
    """Require workflow metadata to exist (fail-closed)."""
    meta = read_json_or_none(meta_path(tenant_id, wid, forge_paths))
    if meta is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "workflow not found")
    return meta


# ── Chat persistence ──────────────────────────────────────────────────

def append_chat_line(tenant_id: str, wid: str, line: dict[str, Any], forge_paths) -> None:
    """Append a JSON line to chat JSONL with bounded file locking.

    Prevents concurrent appends from interleaving (corrupting JSONL).
    Uses bounded_flock: raises WorkflowLockBusy at timeout rather than hanging.
    """
    path = chat_path(tenant_id, wid, forge_paths)
    lock_path = path.with_suffix(".append.lock")
    ensure_dir(path.parent)

    with bounded_flock(lock_path, f"workflow chat append {wid!r}"):
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(line, ensure_ascii=False) + "\n")


async def append_chat_line_async(
    tenant_id: str,
    wid: str,
    sender: str,
    content: str,
    forge_paths=None,
    timestamp: str | None = None,
) -> None:
    """Append a chat message to workflow design session (async variant).

    Args:
        tenant_id: Tenant ID
        wid: Workflow ID
        sender: Message sender (e.g., "user", "assistant", "system")
        content: Message content
        forge_paths: Path resolver (if None, falls back to default)
        timestamp: ISO timestamp (default: current UTC time)

    Appends to chat JSONL file atomically.
    """
    if timestamp is None:
        timestamp = datetime.utcnow().isoformat() + 'Z'

    if forge_paths is None:
        # Fallback: use default forge paths
        raise ValueError("forge_paths required for append_chat_line_async")

    path = chat_path(tenant_id, wid, forge_paths)
    ensure_dir(path.parent)

    entry = {
        'timestamp': timestamp,
        'sender': sender,
        'content': content,
    }

    # Append to chat JSONL (async, non-blocking)
    async with aiofiles.open(path, 'a', encoding='utf-8') as f:
        await f.write(json.dumps(entry, ensure_ascii=False) + '\n')
