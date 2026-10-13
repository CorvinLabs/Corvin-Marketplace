"""Per-tenant asset store (ADR-2249 D3, PLAN-0947 P3, T-0111):
``<base>/assets/<ast_8hex>/{asset.json,image.png}``.

``base`` is the host's tenant directory (the one ``VideoStorage`` gets), so a tenant can only ever
reach its own assets. An asset is immutable. The image is PNG only and is RE-ENCODED from its pixels:
nothing of the upload's container survives (EXIF, text chunks, ICC profile, trailing bytes); the
caption and the hotspots are typed or placed by the user and are never derived from page content;
the provenance is reduced to ``scheme://host/path``. Ids are validated before they touch a path,
nothing follows a symlink, and every read re-validates the document (a hand-edited file is refused).

The job process binds the store of ITS tenant explicitly (``bound(storage_base)``); ``still`` scenes
resolve their ``asset`` through it. Unbound means no assets: a ``still`` scene fails closed.
"""

from __future__ import annotations

import contextlib
import contextvars
import io
import json
import os
import re
import secrets
import shutil
import stat
import tempfile
import time
import unicodedata
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional
from urllib.parse import urlsplit

ID_RE = re.compile(r"ast_[0-9a-f]{8}")
SPOT_RE = re.compile(r"[a-z0-9_]{2,32}")
USER_RE = re.compile(r"[A-Za-z0-9_.@:+\-]{1,128}")

MAX_ASSETS = 50
MAX_IMAGE_BYTES = 4 * 1024 * 1024   # re-encoded; a 1920x1080 photo-heavy page is ~2 MB (measured 2026-10-13)
MAX_UPLOAD_BYTES = 8 * 1024 * 1024
MAX_DIM = 4096
MIN_DIM = 16
MAX_PIXELS = 12_000_000
MAX_CAPTION = 160
MAX_SPOTS = 8
MAX_SPOT_DESC = 120
MAX_JSON_BYTES = 16 * 1024
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


class AssetError(ValueError):
    """A refusal whose message is safe to show to the user."""


class AssetNotFound(KeyError):
    pass


class AssetQuotaExceeded(AssetError):
    pass


class AssetNotRecorded(AssetError):
    pass


_BIDI = {0x200E, 0x200F, 0x061C, *range(0x202A, 0x202F), *range(0x2066, 0x206A)}


def _clean_text(value: Any, limit: int, what: str, required: bool = True) -> str:
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise AssetError(f"{what} must be text")
    out = "".join(" " if ch.isspace() else ch for ch in value
                  if not (unicodedata.category(ch) in ("Cc", "Cf") and not ch.isspace()) and ord(ch) not in _BIDI)
    out = " ".join(out.split())
    if required and not out:
        raise AssetError(f"{what} is required")
    if len(out) > limit:
        raise AssetError(f"{what} is longer than {limit} characters")
    return out


def sanitise_provenance(value: Any) -> str:
    if value is None or value == "":
        return ""
    if not isinstance(value, str) or len(value) > 2048:
        raise AssetError("source must be a short http(s) address")
    try:
        parts = urlsplit(value.strip())
        host = parts.hostname
    except ValueError:
        raise AssetError("source must be a valid http(s) address") from None
    if parts.scheme not in ("http", "https") or not host:
        raise AssetError("source must be an http(s) address")
    path = "".join(ch for ch in parts.path if ch.isprintable() and not ch.isspace())
    shown = f"[{host.lower()}]" if ":" in host else host.lower()   # urlsplit strips an IPv6 literal's brackets
    out = f"{parts.scheme}://{shown}{path}"
    return out[:200]


def _validate_hotspots(value: Any) -> List[Dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > MAX_SPOTS:
        raise AssetError(f"hotspots must be a list of at most {MAX_SPOTS}")
    out, seen = [], set()
    for h in value:
        if not isinstance(h, dict) or set(h) - {"name", "x", "y", "description"}:
            raise AssetError("a hotspot is {name, x, y, description}")
        name = h.get("name")
        if not isinstance(name, str) or not SPOT_RE.fullmatch(name):
            raise AssetError("a hotspot name is 2-32 characters of a-z, 0-9 and _")
        if name in seen:
            raise AssetError(f"hotspot {name!r} appears twice")
        seen.add(name)
        xy = []
        for k in ("x", "y"):
            v = h.get(k)
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 <= v <= 1 or v != v:
                raise AssetError("hotspot x and y are numbers from 0 to 1 (the point you clicked in the image)")
            xy.append(round(float(v), 4))
        out.append({"name": name, "x": xy[0], "y": xy[1],
                    "description": _clean_text(h.get("description"), MAX_SPOT_DESC, "a hotspot description", False)})
    return out


def validate_meta(caption: Any, hotspots: Any) -> Dict[str, Any]:
    """The caption and hotspots exactly as ``add`` would store them, or AssetError - so a caller can
    refuse bad input BEFORE it spends a fetch or a render on the image."""
    return {"caption": _clean_text(caption, MAX_CAPTION, "the caption"), "hotspots": _validate_hotspots(hotspots)}


def reencode_png(data: bytes) -> Dict[str, Any]:
    if not isinstance(data, (bytes, bytearray)) or not data:
        raise AssetError("the image is empty")
    if len(data) > MAX_UPLOAD_BYTES:
        raise AssetError(f"the image is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB")
    if bytes(data[:8]) != PNG_MAGIC:
        raise AssetError("only PNG images are accepted")
    try:
        from PIL import Image
    except ImportError:
        raise AssetError("image support is not installed on this host") from None
    try:
        with Image.open(io.BytesIO(bytes(data)), formats=("PNG",)) as img:
            w, h = img.size
            if getattr(img, "n_frames", 1) > 1:
                raise AssetError("animated images are not accepted")
            if not (MIN_DIM <= w <= MAX_DIM and MIN_DIM <= h <= MAX_DIM) or w * h > MAX_PIXELS:
                raise AssetError(f"the image must be {MIN_DIM}-{MAX_DIM} pixels per side and at most "
                                 f"{MAX_PIXELS // 1_000_000} megapixels")
            img.load()
            has_alpha = img.mode in ("RGBA", "LA", "PA") or "transparency" in img.info
            work = img.convert("RGBA" if has_alpha else "RGB")
            clean = Image.frombytes(work.mode, work.size, work.tobytes())
    except AssetError:
        raise
    except Image.DecompressionBombError:
        raise AssetError(f"the image must be {MIN_DIM}-{MAX_DIM} pixels per side and at most "
                         f"{MAX_PIXELS // 1_000_000} megapixels") from None
    except Exception:
        raise AssetError("this is not a readable PNG image") from None
    out = io.BytesIO()
    clean.save(out, format="PNG", optimize=True)
    png = out.getvalue()
    if len(png) > MAX_IMAGE_BYTES:
        raise AssetError(f"the image is larger than {MAX_IMAGE_BYTES // (1024 * 1024)} MB after it was re-encoded; "
                         "use a smaller or simpler image")
    return {"png": png, "width": w, "height": h}


def _read_regular(path: Path, limit: int) -> bytes:
    fd = os.open(str(path), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size > limit:
            raise AssetError("a stored asset file is not a regular file within its size limit")
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
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


@contextlib.contextmanager
def _exclusive(path: Path) -> Iterator[None]:
    fd = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        try:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX)
        except ImportError:
            import msvcrt
            for _ in range(200):
                try:
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    time.sleep(0.05)
            else:
                raise AssetError("the asset store is busy; try again")
        yield
    finally:
        os.close(fd)


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class AssetStore:
    def __init__(self, base_path: str):
        if not base_path:
            raise ValueError("AssetStore needs the host's tenant directory")
        self.root = Path(base_path) / "assets"

    def _dir(self, asset_id: str) -> Path:
        if not isinstance(asset_id, str) or not ID_RE.fullmatch(asset_id):
            raise AssetNotFound(asset_id)
        return self.root / asset_id

    def ids(self) -> List[str]:
        try:
            return sorted(p.name for p in self.root.iterdir()
                          if ID_RE.fullmatch(p.name) and p.is_dir() and not p.is_symlink())
        except OSError:
            return []

    def _new_id(self) -> str:
        existing = set(self.ids())
        while True:
            aid = "ast_" + secrets.token_hex(4)
            if aid not in existing:
                return aid

    def add(self, png_bytes: bytes, *, caption: Any, uploaded_by: Any, source: Any = None,
            hotspots: Any = None, before_commit: Optional[Callable[[Dict[str, Any]], bool]] = None) -> Dict[str, Any]:
        """Store one image. ``before_commit(doc)`` runs after validation, quota and id allocation and
        BEFORE the asset becomes visible; a falsy return (the host's audit record did not commit)
        aborts the upload with nothing stored - the audit-first order of ADR-2249 invariant 6."""
        if not isinstance(uploaded_by, str) or not USER_RE.fullmatch(uploaded_by):
            raise AssetError("an asset needs the uploading user's id")
        img = reencode_png(png_bytes)
        doc = {"caption": _clean_text(caption, MAX_CAPTION, "the caption"),
               "uploaded_by": uploaded_by, "source": sanitise_provenance(source),
               "hotspots": _validate_hotspots(hotspots),
               "width": img["width"], "height": img["height"], "bytes": len(img["png"]), "created": _now()}
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        staging = self.root / f".new.{secrets.token_hex(4)}"
        try:
            staging.mkdir(mode=0o700)
            _atomic_write(staging / "image.png", img["png"])
            with _exclusive(self.root / ".lock"):
                if len(self.ids()) >= MAX_ASSETS:
                    raise AssetQuotaExceeded(f"at most {MAX_ASSETS} images per workspace; delete one first")
                doc["id"] = self._new_id()
                if before_commit is not None and not before_commit(dict(doc)):
                    raise AssetNotRecorded("the upload could not be recorded; nothing was stored")
                _atomic_write(staging / "asset.json", json.dumps(doc, indent=2, sort_keys=True).encode())
                os.rename(staging, self.root / doc["id"])
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        return dict(doc)

    def has_room(self) -> bool:
        """Whether one more asset fits the quota now - for a caller about to spend a fetch on it. ``add``
        re-checks under the store lock, so a race still ends in AssetQuotaExceeded, never over quota."""
        return len(self.ids()) < MAX_ASSETS

    def update(self, asset_id: str, *, caption: Any = None, hotspots: Any = None,
               before_commit: Optional[Callable[[Dict[str, Any]], bool]] = None) -> Dict[str, Any]:
        """Change an asset's caption and/or hotspots (the image never changes). ``None`` keeps a field.
        ``before_commit(doc)`` runs with the new document before it is written; falsy = nothing changes."""
        with _exclusive(self.root / ".lock"):
            doc = self.get(asset_id, with_png=False)
            new = dict(doc)
            if caption is not None:
                new["caption"] = _clean_text(caption, MAX_CAPTION, "the caption")
            if hotspots is not None:
                new["hotspots"] = _validate_hotspots(hotspots)
            if before_commit is not None and not before_commit(dict(new)):
                raise AssetNotRecorded("the change could not be recorded; nothing was changed")
            _atomic_write(self._dir(asset_id) / "asset.json", json.dumps(new, indent=2, sort_keys=True).encode())
        return new

    def get(self, asset_id: str, *, with_png: bool = True) -> Dict[str, Any]:
        d = self._dir(asset_id)
        if d.is_symlink() or not d.is_dir():
            raise AssetNotFound(asset_id)
        try:
            doc = json.loads(_read_regular(d / "asset.json", MAX_JSON_BYTES).decode("utf-8"))
            if with_png:
                png = _read_regular(d / "image.png", MAX_IMAGE_BYTES)
            else:
                st = os.lstat(d / "image.png")
                if not stat.S_ISREG(st.st_mode) or st.st_size > MAX_IMAGE_BYTES:
                    raise AssetError("a stored asset is invalid")
                png = None
        except (OSError, ValueError):
            raise AssetError("a stored asset is unreadable") from None
        if not isinstance(doc, dict) or doc.get("id") != asset_id \
                or (png is not None and (len(png) > MAX_IMAGE_BYTES or not png.startswith(PNG_MAGIC))):
            raise AssetError("a stored asset is invalid")
        try:
            _clean_text(doc.get("caption"), MAX_CAPTION, "the caption")
            _validate_hotspots(doc.get("hotspots"))
            w, h = int(doc["width"]), int(doc["height"])
            if not (MIN_DIM <= w <= MAX_DIM and MIN_DIM <= h <= MAX_DIM) or w * h > MAX_PIXELS:
                raise AssetError("a stored asset is invalid")
            src = doc.get("source", "")
            if not isinstance(src, str) or (src and sanitise_provenance(src) != src):
                raise AssetError("a stored asset is invalid")
            who = doc.get("uploaded_by")
            if not isinstance(who, str) or not USER_RE.fullmatch(who):
                raise AssetError("a stored asset is invalid")
            n_bytes = doc["bytes"]
            if isinstance(n_bytes, bool) or not isinstance(n_bytes, int) or n_bytes < 0 or not isinstance(doc["created"], str):
                raise AssetError("a stored asset is invalid")
        except (AssetError, KeyError, TypeError, ValueError):
            raise AssetError("a stored asset is invalid") from None
        return {**doc, "png": png} if with_png else dict(doc)

    def public(self, asset_id: str) -> Dict[str, Any]:
        return self.get(asset_id, with_png=False)

    def list(self) -> List[Dict[str, Any]]:
        out = []
        for aid in self.ids():
            try:
                out.append(self.public(aid))
            except (AssetError, AssetNotFound):
                continue
        return out

    def catalogue(self) -> Dict[str, Dict[str, Any]]:
        return {a["id"]: {"caption": a["caption"], "width": a["width"], "height": a["height"],
                          "spots": {h["name"]: h for h in a["hotspots"]}} for a in self.list()}

    def delete(self, asset_id: str) -> None:
        d = self._dir(asset_id)
        if d.is_symlink() or not d.is_dir():
            raise AssetNotFound(asset_id)
        shutil.rmtree(d)



# ── asset_hygiene (ADR-2249 D5): what a stored or published asset may carry ────────────────────────
# The re-encoder writes exactly these chunks; anything else (eXIf, tEXt/iTXt/zTXt, iCCP, tIME, a
# private chunk, bytes after IEND) is metadata that should not have survived.
PNG_ALLOWED_CHUNKS = frozenset({"IHDR", "PLTE", "tRNS", "IDAT", "IEND"})


def png_chunks(png: bytes) -> List[str]:
    """Chunk types in file order; a trailing-garbage or truncated file yields a final ``"<trailing>"``."""
    import struct  # noqa: PLC0415

    out, pos = [], 8
    if not bytes(png[:8]) == PNG_MAGIC:
        return ["<not-png>"]
    while pos + 8 <= len(png):
        n = struct.unpack(">I", png[pos:pos + 4])[0]
        kind = png[pos + 4:pos + 8].decode("latin-1")
        out.append(kind)
        pos += 12 + n
        if kind == "IEND":
            break
    if pos != len(png):
        out.append("<trailing>")
    return out


def hygiene_findings(png: Optional[bytes], doc: Dict[str, Any]) -> List[str]:
    """Every way one asset breaks D3/D5 (empty = clean): metadata chunks, size and dimension caps, a
    provenance that kept a query, fragment or userinfo. Pure; used by the asset_hygiene signal."""
    found: List[str] = []
    if png is not None:
        extra = sorted(set(png_chunks(png)) - PNG_ALLOWED_CHUNKS)
        if extra:
            found.append("metadata:" + ",".join(extra))
        if len(png) > MAX_IMAGE_BYTES:
            found.append("size")
    try:
        w, h = int(doc.get("width")), int(doc.get("height"))
        if not (MIN_DIM <= w <= MAX_DIM and MIN_DIM <= h <= MAX_DIM) or w * h > MAX_PIXELS:
            found.append("dimensions")
    except (TypeError, ValueError):
        found.append("dimensions")
    src = doc.get("source") or ""
    try:
        clean = isinstance(src, str) and not any(c in src for c in "?#") and (not src or sanitise_provenance(src) == src)
    except AssetError:
        clean = False
    if not clean:
        found.append("provenance")
    return found


_BOUND: "contextvars.ContextVar[Optional[AssetStore]]" = contextvars.ContextVar("vp_asset_store", default=None)


@contextlib.contextmanager
def bound(storage_base: Optional[str]) -> Iterator[Optional[AssetStore]]:
    store = AssetStore(storage_base) if storage_base else None
    token = _BOUND.set(store)
    try:
        yield store
    finally:
        _BOUND.reset(token)


def current() -> Optional[AssetStore]:
    return _BOUND.get()
