"""Per-tenant style store (PLAN-0945 P2): ``<base>/styles/<style_id>/{style.json,logo.png}``.

``base`` is the host's tenant directory (the same one ``VideoStorage`` gets), so a tenant can only
ever reach its own styles. Ids are validated before they touch a path, nothing follows a symlink,
and every read re-validates the document (a hand-edited file is refused, not trusted).
"""

from __future__ import annotations

import contextlib
import json
import os
import secrets
import shutil
import stat
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional

try:
    from .style_pack import ID_RE, MAX_JSON_BYTES, Style, StyleError, style_from_json, validate_style
except ImportError:  # standalone script use
    from style_pack import ID_RE, MAX_JSON_BYTES, Style, StyleError, style_from_json, validate_style

MAX_STYLES = 20


class StyleNotFound(KeyError):
    pass


class StyleQuotaExceeded(StyleError):
    pass


def _read_regular(path: Path, limit: int) -> bytes:
    """Read a regular file without following a symlink; refuse anything else."""
    fd = os.open(str(path), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size > limit:
            raise StyleError("stored style file is not a regular file within its size limit")
        with os.fdopen(fd, "rb", closefd=False) as f:
            return f.read(limit + 1)
    finally:
        os.close(fd)


def _atomic_write(path: Path, data: bytes) -> None:
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


@contextlib.contextmanager
def _exclusive(path: Path):
    """Cross-process (and cross-thread) mutual exclusion: an OS lock on ``path``, released on crash."""
    fd = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        try:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX)
        except ImportError:  # Windows
            import msvcrt
            for _ in range(200):
                try:
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    time.sleep(0.05)
            else:
                raise StyleError("the style store is busy; try again")
        yield
    finally:
        os.close(fd)  # closing releases either kind of lock


def write_style_snapshot(style: Style, directory: Path) -> None:
    """Write style.json (+ logo) into ``directory``: the copy that travels with a video."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    _atomic_write(directory / "style.json", json.dumps(style.to_json(), indent=2, sort_keys=True).encode())
    if style.mark_png:
        _atomic_write(directory / "logo.png", style.mark_png)


def _read_style_dir(d: Path) -> Style:
    """Read + fully re-validate a style directory. Raises StyleError (message safe to show)."""
    try:
        doc = json.loads(_read_regular(d / "style.json", MAX_JSON_BYTES).decode("utf-8"))
        logo = d / "logo.png"
        mark = _read_regular(logo, 2 * 1024 * 1024 + 1) if logo.exists() or logo.is_symlink() else None
    except (OSError, ValueError):
        raise StyleError("stored style is unreadable") from None
    return style_from_json(doc, mark_png=mark)


def load_snapshot(directory: Path) -> Optional[Style]:
    """Read back the style a video was rendered with (``videos/<job>/style``).

    None ONLY when the video has no snapshot (the built-in look). A snapshot that exists but is
    unreadable or invalid raises StyleError: silently falling back to the Corvin look would
    misreport a custom-styled video."""
    d = Path(directory)
    if not d.is_symlink() and not (d / "style.json").exists() and not (d / "style.json").is_symlink():
        return None
    if d.is_symlink():
        raise StyleError("stored style is unreadable")
    return _read_style_dir(d)


class StyleStore:
    def __init__(self, base_path: str):
        if not base_path:
            raise ValueError("StyleStore needs the host's tenant directory")
        self.root = Path(base_path) / "styles"
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def _dir(self, style_id: str) -> Path:
        if not isinstance(style_id, str) or not ID_RE.fullmatch(style_id):
            raise StyleNotFound(style_id)
        return self.root / style_id

    def ids(self) -> List[str]:
        return sorted(p.name for p in self.root.iterdir()
                      if ID_RE.fullmatch(p.name) and p.is_dir() and not p.is_symlink())

    def new_id(self) -> str:
        existing = set(self.ids())
        while True:
            sid = "sty_" + secrets.token_hex(4)
            if sid not in existing:
                return sid

    def save(self, style: Style) -> Style:
        """Validate and store. A style is immutable: saving an existing id is refused."""
        validate_style(style)
        d = self._dir(style.id)
        if d.exists():
            raise StyleError("a style with this id already exists")
        staging = self.root / f".{style.id}.{secrets.token_hex(3)}.new"
        try:
            staging.mkdir(mode=0o700)
            write_style_snapshot(style, staging)
            with _exclusive(self.root / ".lock"):  # quota check and rename are one step
                if d.exists():
                    raise StyleError("a style with this id already exists")
                if len(self.ids()) >= MAX_STYLES:
                    raise StyleQuotaExceeded(f"at most {MAX_STYLES} styles per tenant; delete one first")
                os.rename(staging, d)
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        return style

    def load(self, style_id: str) -> Style:
        d = self._dir(style_id)
        if d.is_symlink() or not d.is_dir():
            raise StyleNotFound(style_id)
        if not (d / "style.json").exists() and not (d / "style.json").is_symlink():
            raise StyleNotFound(style_id)
        return _read_style_dir(d)

    def list(self) -> List[Style]:
        out = []
        for sid in self.ids():
            try:
                out.append(self.load(sid))
            except (StyleError, StyleNotFound):
                continue  # a damaged style is skipped, never rendered
        return out

    def delete(self, style_id: str) -> None:
        d = self._dir(style_id)
        if not d.is_dir() or d.is_symlink():
            raise StyleNotFound(style_id)
        shutil.rmtree(d)
        if self.get_default() == style_id:
            self.set_default(None)

    # ── tenant default ──
    def get_default(self) -> Optional[str]:
        try:
            sid = _read_regular(self.root / "default", 64).decode("ascii").strip()
        except (OSError, UnicodeDecodeError, StyleError):
            return None
        return sid if ID_RE.fullmatch(sid) and (self.root / sid).is_dir() else None

    def set_default(self, style_id: Optional[str]) -> None:
        if style_id is None:
            try:
                (self.root / "default").unlink()
            except FileNotFoundError:
                pass
            return
        self._dir(style_id)
        if not (self.root / style_id).is_dir():
            raise StyleNotFound(style_id)
        _atomic_write(self.root / "default", style_id.encode("ascii"))

    def erase_all(self) -> int:
        """GDPR Art. 17: remove every stored style of this tenant."""
        n = len(self.ids())
        shutil.rmtree(self.root, ignore_errors=True)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        return n
