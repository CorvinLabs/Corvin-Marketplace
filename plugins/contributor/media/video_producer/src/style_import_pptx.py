"""PowerPoint (.pptx/.potx) -> draft Style (PLAN-0945 P2).

Pure function over bytes: no filesystem writes, no network, no subprocess. The upload is
untrusted: the zip is sniffed (never the extension), bounded while reading, never extracted,
XML is parsed with stdlib ElementTree after refusing any DOCTYPE/ENTITY, and images are
re-encoded to PNG by Pillow. Slide text, notes, comments and docProps are never read.
"""

from __future__ import annotations

import colorsys
import copy
import hashlib
import io
import posixpath
import re
import stat
import time
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

try:
    from .style_pack import (MAX_ASSET_BYTES, MAX_NAME, Style, StyleError, contrast, luminance, mix, rgba,
                             sanitize_source, validate_style)
    from .web_templates import load_tokens
except ImportError:  # standalone script use
    from style_pack import (MAX_ASSET_BYTES, MAX_NAME, Style, StyleError, contrast, luminance, mix, rgba,
                            sanitize_source, validate_style)
    from web_templates import load_tokens

MAX_UPLOAD = 25 * 1024 * 1024
MAX_ENTRIES = 1500  # real decks reach 750 parts; the uncompressed-size cap is the actual bomb guard
MAX_TOTAL_UNCOMPRESSED = 150 * 1024 * 1024
RATIO_CAP = 100  # applies to entries larger than RATIO_MIN
RATIO_MIN = 1_000_000
MAX_XML_BYTES = 8 * 1024 * 1024
MAX_MEDIA_BYTES = 10 * 1024 * 1024
MAX_XML_NODES = 300_000
MAX_XML_DEPTH = 64
MAX_XML_NODES_TOTAL = 1_500_000  # all parts of one import together (a 94 KB zip can hold 8M nodes)
MAX_IMPORT_SECONDS = 8.0
TOO_COMPLEX = "The presentation is too complex to read."
LOGO_MIN_CONTRAST = 1.5
MAX_XML_BUDGET = 60 * 1024 * 1024  # all XML parts together
MAX_LAYOUTS = 200
MAX_MASTERS = 5
MAX_IMAGE_PIXELS = 16_000_000
LOGO_MAX_PX = 1024
NEUTRAL_ACCENT = "#5a7da8"

A = "http://schemas.openxmlformats.org/drawingml/2006/main"
P = "http://schemas.openxmlformats.org/presentationml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
REL = "http://schemas.openxmlformats.org/package/2006/relationships"
CT = "http://schemas.openxmlformats.org/package/2006/content-types"

# (accent1, accent2) pairs of the stock Office / default themes, measured on real decks
OFFICE_DEFAULTS = {
    ("4f81bd", "c0504d"): "Office 2007-2010",
    ("4472c4", "ed7d31"): "Office 2013-2022",
    ("5b9bd5", "ed7d31"): "Office 2013",
    ("156082", "e97132"): "Office 2023",
    ("058dc7", "50b432"): "default",
}

_SERIF = ("times", "georgia", "cambria", "garamond", "palatino", "minion", "baskerville", "bodoni", "didot",
          "century", "caslon", "book antiqua", "bookman", "constantia", "sitka", "roman", "serif")
_MONO = ("consolas", "courier", "menlo", "monaco", "mono", "code", "typewriter", "lucida console")
_SANS = ("arial", "helvetica", "calibri", "aptos", "segoe", "verdana", "tahoma", "trebuchet", "sans",
         "grotesk", "gothic", "roboto", "open", "fira", "inter", "lato", "source", "noto", "ubuntu", "franklin")


class PptxImportError(StyleError):
    """The file cannot be imported; the message is safe to show the user."""


@dataclass
class ImportResult:
    style: Style
    notes: List[str] = field(default_factory=list)


# ── zip package ─────────────────────────────────────────────────────────────

class _Package:
    def __init__(self, data: bytes) -> None:
        self.xml_budget = MAX_XML_BUDGET
        self.total_budget = MAX_TOTAL_UNCOMPRESSED
        self.nodes_left = MAX_XML_NODES_TOTAL
        self.deadline = time.monotonic() + MAX_IMPORT_SECONDS
        try:
            self.zf = zipfile.ZipFile(io.BytesIO(data))
            infos = self.zf.infolist()
        except PptxImportError:
            raise
        except Exception:  # noqa: BLE001 — truncated/garbled central directory
            raise PptxImportError("This file is not a readable PowerPoint presentation.") from None
        if len(infos) > MAX_ENTRIES:
            raise PptxImportError(f"The presentation has too many parts ({len(infos)}; limit {MAX_ENTRIES}).")
        self.infos: Dict[str, zipfile.ZipInfo] = {}
        seen = set()
        declared = 0
        for info in infos:
            name = info.filename
            self._check_name(name)
            key = name.casefold()
            if key in seen:
                raise PptxImportError("The presentation contains duplicate part names and was refused.")
            seen.add(key)
            mode = (info.external_attr >> 16) & 0xFFFF
            if stat.S_ISLNK(mode):
                raise PptxImportError("The presentation contains a symbolic link and was refused.")
            if info.flag_bits & 0x1:
                raise PptxImportError("The presentation is encrypted and cannot be read.")
            if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                raise PptxImportError("The presentation uses an unsupported compression method.")
            declared += info.file_size
            self.infos[name] = info
        if declared > MAX_TOTAL_UNCOMPRESSED:
            raise PptxImportError("The presentation would expand to more than 150 MB and was refused.")
        for info in infos:
            if info.file_size > RATIO_MIN and info.file_size > RATIO_CAP * max(info.compress_size, 1):
                raise PptxImportError("The presentation has a suspicious compression ratio and was refused.")

    @staticmethod
    def _check_name(name: str) -> None:
        bad = (not name or len(name) > 260 or "\\" in name or "\x00" in name or name.startswith("/")
               or re.match(r"^[A-Za-z]:", name) is not None
               or any(part in ("..", ".") for part in name.split("/")))
        if bad:
            raise PptxImportError("The presentation contains an unsafe part name and was refused.")

    def has(self, name: str) -> bool:
        return name in self.infos

    def names(self, prefix: str) -> List[str]:
        return sorted((n for n in self.infos if n.startswith(prefix) and not n.endswith("/")),
                      key=lambda n: (len(n), n))

    def read(self, name: str, cap: int) -> Optional[bytes]:
        """Bounded read; None when the part is absent. Over ``cap`` -> OverflowError."""
        info = self.infos.get(name)
        if info is None:
            return None
        if info.file_size > cap:
            raise OverflowError(name)
        out = bytearray()
        try:
            with self.zf.open(info) as f:
                while True:
                    chunk = f.read(65536)
                    if not chunk:
                        break
                    out += chunk
                    if len(out) > info.file_size or len(out) > cap:
                        raise PptxImportError("A part of the presentation is larger than it declares.")
        except PptxImportError:
            raise
        except Exception:  # noqa: BLE001 — CRC error, corrupt stream
            raise PptxImportError("This file is not a readable PowerPoint presentation.") from None
        self.total_budget -= len(out)
        if self.total_budget < 0:
            raise PptxImportError("The presentation expands to more than 150 MB and was refused.")
        return bytes(out)

    def xml(self, name: str) -> Optional[ET.Element]:
        try:
            raw = self.read(name, MAX_XML_BYTES)
        except OverflowError:
            raise PptxImportError("A part of the presentation is too large to read safely.") from None
        if raw is None:
            return None
        self.xml_budget -= len(raw)
        if self.xml_budget < 0:
            raise PptxImportError("The presentation holds too much XML and was refused.")
        self.check_time()
        return parse_xml(raw, self)

    def check_time(self) -> None:
        if time.monotonic() > self.deadline:
            raise PptxImportError(TOO_COMPLEX)

    def rels(self, part: str) -> List[Dict[str, Any]]:
        d, base = posixpath.split(part)
        root = self.xml(posixpath.join(d, "_rels", base + ".rels"))
        return parse_rels(root, part) if root is not None else []


def parse_xml(raw: bytes, pkg: Optional["_Package"] = None) -> ET.Element:
    """Hardened parse: no DTD/entities, NUL-free (no UTF-16 smuggling), node and depth caps.
    With ``pkg`` the node count also draws on the import-wide node and time budgets."""
    low = raw.lower()
    if b"\x00" in raw:
        raise PptxImportError("The presentation uses an unsupported text encoding.")
    if b"<!doctype" in low or b"<!entity" in low:
        raise PptxImportError("The presentation contains a document type declaration and was refused.")
    parser = ET.XMLPullParser(events=("start", "end"))
    root: Optional[ET.Element] = None
    depth = nodes = 0
    limit = min(MAX_XML_NODES, pkg.nodes_left) if pkg is not None else MAX_XML_NODES
    try:
        for i in range(0, len(raw), 65536):
            if pkg is not None:
                pkg.check_time()
            parser.feed(raw[i:i + 65536])
            for ev, el in parser.read_events():
                if ev == "start":
                    if root is None:
                        root = el
                    depth += 1
                    nodes += 1
                    if depth > MAX_XML_DEPTH or nodes > limit:
                        if pkg is not None and nodes <= MAX_XML_NODES and depth <= MAX_XML_DEPTH:
                            raise PptxImportError(TOO_COMPLEX)
                        raise PptxImportError("The presentation contains oversized or deeply nested XML.")
                else:
                    depth -= 1
        parser.close()
    except PptxImportError:
        raise
    except ET.ParseError:
        raise PptxImportError("The presentation contains malformed XML.") from None
    if root is None:
        raise PptxImportError("The presentation contains an empty XML part.")
    if pkg is not None:
        pkg.nodes_left -= nodes
    return root


def parse_rels(root: ET.Element, part: str) -> List[Dict[str, Any]]:
    out = []
    base = posixpath.dirname(part)
    for r in root.iter(f"{{{REL}}}Relationship"):
        target = r.get("Target") or ""
        external = (r.get("TargetMode") or "").lower() == "external"
        path = None
        if not external and target:
            joined = target.lstrip("/") if target.startswith("/") else posixpath.join(base, target)
            norm = posixpath.normpath(joined)
            if not norm.startswith("..") and not norm.startswith("/") and "\\" not in norm:
                path = norm
        out.append({"id": r.get("Id") or "", "type": (r.get("Type") or "").rsplit("/", 1)[-1],
                    "external": external, "path": path})
    return out


# ── colours ─────────────────────────────────────────────────────────────────

_HEX6 = re.compile(r"[0-9A-Fa-f]{6}")
_SYS = {"windowtext": "000000", "window": "ffffff"}
_SCHEME_KEYS = ("dk1", "lt1", "dk2", "lt2", "accent1", "accent2", "accent3", "accent4", "accent5", "accent6")


@dataclass
class _Ctx:
    scheme: Dict[str, str]
    clrmap: Dict[str, str] = field(default_factory=lambda: {"bg1": "lt1", "tx1": "dk1", "bg2": "lt2", "tx2": "dk2"})


def _lum_mod(hexcol: str, mod: float, off: float) -> str:
    r, g, b = (int(hexcol[i:i + 2], 16) / 255 for i in (0, 2, 4))
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    l = max(0.0, min(1.0, l * mod + off))
    r, g, b = colorsys.hls_to_rgb(h, l, s)
    return "%02x%02x%02x" % (round(r * 255), round(g * 255), round(b * 255))


def color_of(el: Optional[ET.Element], ctx: _Ctx) -> Optional[str]:
    """First colour child of ``el`` as lowercase rrggbb, with lumMod/lumOff/tint/shade applied."""
    if el is None:
        return None
    for child in el:
        tag = child.tag.rsplit("}", 1)[-1]
        base: Optional[str] = None
        if tag == "srgbClr" and _HEX6.fullmatch(child.get("val") or ""):
            base = child.get("val").lower()
        elif tag == "sysClr":
            last = child.get("lastClr") or ""
            base = last.lower() if _HEX6.fullmatch(last) else _SYS.get((child.get("val") or "").lower())
        elif tag == "schemeClr":
            key = child.get("val") or ""
            key = ctx.clrmap.get(key, key)
            base = ctx.scheme.get(key)
        if base is None:
            continue
        for m in child:
            mt = m.tag.rsplit("}", 1)[-1]
            try:
                v = int(m.get("val") or 0) / 100000
            except ValueError:
                continue
            if mt == "lumMod":
                base = _lum_mod(base, v, 0)
            elif mt == "lumOff":
                base = _lum_mod(base, 1, v)
            elif mt == "tint":
                base = mix("#" + base, "#ffffff", 1 - v)[1:]
            elif mt == "shade":
                base = mix("#" + base, "#000000", 1 - v)[1:]
        return base
    return None


def _hsv(hexcol: str) -> Tuple[float, float, float]:
    return colorsys.rgb_to_hsv(*(int(hexcol[i:i + 2], 16) / 255 for i in (0, 2, 4)))


def _is_chromatic(hexcol: str) -> bool:
    _, s, v = _hsv(hexcol)
    return s >= 0.28 and 0.15 <= v <= 0.98


def read_scheme(theme: ET.Element) -> Tuple[Dict[str, str], str, str]:
    scheme: Dict[str, str] = {}
    cs = theme.find(f".//{{{A}}}clrScheme")
    if cs is not None:
        for key in _SCHEME_KEYS:
            c = cs.find(f"{{{A}}}{key}")
            v = color_of(c, _Ctx({}))
            if v:
                scheme[key] = v
    fonts = []
    for kind in ("majorFont", "minorFont"):
        latin = theme.find(f".//{{{A}}}{kind}/{{{A}}}latin")
        fonts.append(_clean_font(latin.get("typeface") if latin is not None else ""))
    return scheme, fonts[0], fonts[1]


def _clean_font(name: Optional[str]) -> str:
    return re.sub(r"[^\w .\-+]", "", name or "")[:60].strip()


def office_default_name(scheme: Dict[str, str]) -> Optional[str]:
    return OFFICE_DEFAULTS.get((scheme.get("accent1", ""), scheme.get("accent2", "")))


# ── fonts ───────────────────────────────────────────────────────────────────

def map_font(name: str) -> Tuple[str, str]:
    low = name.lower()
    if not low:
        return "Instrument Sans", "no theme font; default sans"
    for fam, keys in (("JetBrains Mono", _MONO), ("Newsreader", _SERIF)):
        if any(k in low for k in keys) and "sans" not in low:
            return fam, f"{'monospaced' if fam == 'JetBrains Mono' else 'serif'} family"
    if any(k in low for k in _SANS):
        return "Instrument Sans", "sans-serif family"
    return "Instrument Sans", "unknown family; default sans"


# ── colour derivation ───────────────────────────────────────────────────────

def _adjust(color: str, bg: str, floor: float) -> Tuple[str, bool]:
    """Move ``color`` minimally toward white (dark bg) or black (light bg) until it meets ``floor``."""
    if contrast(color, bg) >= floor:
        return color, False
    target = "#ffffff" if luminance(bg) < 0.179 else "#000000"
    for i in range(1, 51):
        c = mix(color, target, i * 0.02)
        if contrast(c, bg) >= floor:
            return c, True
    return target, True


def _pick_accent(cands: List[str], bg: str) -> Tuple[str, bool]:
    for c in cands:
        if contrast(c, bg) >= 3.05:
            return c, False
    return _adjust(cands[0], bg, 3.05)


def _palette(bg: str, text: str, accents: List[str], success: str) -> Tuple[Dict[str, str], bool]:
    dark = luminance(bg) < 0.179
    text, _ = _adjust(text, bg, 7.0)
    accent, adjusted = _pick_accent(accents, bg)
    hi = mix(accent, "#ffffff", 0.3) if dark else mix(accent, "#ffffff", 0.2)
    if contrast(hi, bg) < 1.9:
        hi = accent
    t = 0.4
    muted = mix(text, bg, t)
    while contrast(muted, bg) < 4.0 and t > 0:
        t = max(0.0, t - 0.05)
        muted = mix(text, bg, t)
    card = bg
    for k in (0.05, 0.03, 0.015, 0.0):  # a card must keep both text colours readable
        card = mix(bg, text, k)
        if contrast(card, text) >= 4.5 and contrast(card, muted) >= 3.0:
            break
    return {
        "bg": bg, "bg_card": card, "border": mix(bg, text, 0.14), "text": text,
        "text_muted": muted, "text_faint": mix(text, bg, 0.7), "accent": accent, "accent_hi": hi,
        "glow": rgba(accent, 0.16 if dark else 0.2), "success": success,
    }, adjusted


def _other_bg(deck_dark: bool, scheme: Dict[str, str], neutral: bool) -> str:
    if deck_dark:
        bg = "#f7f7f5" if neutral else "#" + (scheme.get("lt2") or scheme.get("lt1") or "f7f7f5")
        for _ in range(12):
            if luminance(bg) >= 0.85:
                break
            bg = mix(bg, "#ffffff", 0.2)
        return bg
    bg = "#15171c" if neutral else "#" + (scheme.get("dk2") or scheme.get("dk1") or "15171c")
    for _ in range(14):
        if luminance(bg) <= 0.03:
            break
        bg = mix(bg, "#000000", 0.15)
    return bg


# ── master / layout scan ────────────────────────────────────────────────────

@dataclass
class _Pic:
    path: str
    on_master: bool
    layouts: set
    area: float
    corner: bool


@dataclass
class _Scan:
    pics: Dict[str, _Pic] = field(default_factory=dict)
    shape_area: Dict[str, float] = field(default_factory=dict)
    bg: Optional[str] = None
    clrmap: Dict[str, str] = field(default_factory=dict)


def _ext_int(el: Optional[ET.Element], key: str) -> int:
    try:
        return max(0, int(el.get(key) or 0)) if el is not None else 0
    except ValueError:
        return 0


def _scan_part(pkg: _Package, part: str, root: ET.Element, ctx: _Ctx, sld: Tuple[int, int],
               scan: _Scan, is_master: bool, rels: List[Dict[str, Any]], sname: str) -> None:
    by_id = {r["id"]: r for r in rels}
    sw, sh = sld
    for sp in root.iter(f"{{{P}}}sp"):
        sppr = sp.find(f"{{{P}}}spPr")
        if sppr is None:
            continue
        fill = sppr.find(f"{{{A}}}solidFill")
        col = color_of(fill, ctx) if fill is not None else None
        xf = sppr.find(f"{{{A}}}xfrm")
        ext = xf.find(f"{{{A}}}ext") if xf is not None else None
        area = _ext_int(ext, "cx") * _ext_int(ext, "cy") / float(sw * sh)
        if col and area > 0:
            scan.shape_area[col] = scan.shape_area.get(col, 0.0) + min(area, 1.0)
    for pic in root.iter(f"{{{P}}}pic"):
        blip = pic.find(f".//{{{A}}}blip")
        rid = blip.get(f"{{{R}}}embed") if blip is not None else None
        rel = by_id.get(rid or "")
        if rel is None or rel["external"] or not rel["path"] or not rel["path"].startswith("ppt/media/"):
            continue
        xf = pic.find(f"{{{P}}}spPr/{{{A}}}xfrm")
        ext = xf.find(f"{{{A}}}ext") if xf is not None else None
        off = xf.find(f"{{{A}}}off") if xf is not None else None
        cx, cy = _ext_int(ext, "cx"), _ext_int(ext, "cy")
        area = cx * cy / float(sw * sh)
        mx = (_ext_int(off, "x") + cx / 2) / sw
        my = (_ext_int(off, "y") + cy / 2) / sh
        corner = (mx < 0.3 or mx > 0.7) and (my < 0.3 or my > 0.7)
        cur = scan.pics.get(rel["path"])
        if cur is None:
            cur = scan.pics[rel["path"]] = _Pic(rel["path"], False, set(), area, corner)
        if is_master:
            cur.on_master = True
        else:
            cur.layouts.add(sname)
        if cur.area == 0:
            cur.area, cur.corner = area, corner


def _bg_of(root: ET.Element, ctx: _Ctx) -> Optional[str]:
    bg = root.find(f"{{{P}}}cSld/{{{P}}}bg")
    if bg is None:
        return None
    pr = bg.find(f"{{{P}}}bgPr")
    if pr is not None:
        fill = pr.find(f"{{{A}}}solidFill")
        if fill is not None:
            return color_of(fill, ctx)
        grad = pr.find(f"{{{A}}}gradFill/{{{A}}}gsLst/{{{A}}}gs")
        if grad is not None:
            return color_of(grad, ctx)
        return None
    return color_of(bg.find(f"{{{P}}}bgRef"), ctx)


def _pic_score(p: _Pic) -> Tuple[int, str]:
    if p.area >= 0.4 or p.area <= 0:
        return (-1, p.path)
    s = (4 if p.on_master else 0) + min(len(p.layouts), 6) + (3 if p.corner else 0)
    s += 2 if p.area < 0.08 else 1
    return (s, p.path)


# ── images ──────────────────────────────────────────────────────────────────

_MAGIC = (b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"GIF8", b"BM")


def _is_bitmap(raw: bytes) -> bool:
    return raw.startswith(_MAGIC) or (raw[:4] == b"RIFF" and raw[8:12] == b"WEBP")


def _logo_png(raw: bytes) -> Tuple[Optional[bytes], Optional[Any], Optional[str]]:
    """(png, pil_image, problem). Re-encoded RGBA PNG <= 2 MB and <= 1024 px."""
    from PIL import Image
    if not _is_bitmap(raw):
        return None, None, "vector"
    try:
        im = Image.open(io.BytesIO(raw))
        w, h = im.size
        if w < 8 or h < 8:
            return None, None, "tiny"
        if w * h > MAX_IMAGE_PIXELS:
            return None, None, "huge"
        im.load()
        im = im.convert("RGBA")
        im.thumbnail((LOGO_MAX_PX, LOGO_MAX_PX), Image.LANCZOS)
        for limit in (LOGO_MAX_PX, 768, 512, 256):
            im.thumbnail((limit, limit), Image.LANCZOS)
            buf = io.BytesIO()
            im.save(buf, "PNG", optimize=True)
            if buf.tell() <= MAX_ASSET_BYTES:
                return buf.getvalue(), im, None
        return None, None, "huge"
    except Exception:  # noqa: BLE001 — Pillow raises many types on hostile input
        return None, None, "undecodable"


def _image_colors(im: Any) -> List[str]:
    from PIL import Image
    small = im.copy()
    small.thumbnail((96, 96))
    px = [p[:3] for p in small.getdata() if p[3] >= 128]
    if len(px) < 10:
        return []
    flat = Image.new("RGB", (len(px), 1))
    flat.putdata(px)
    q = flat.quantize(colors=6, method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette() or []
    cols = sorted(q.getcolors() or [], key=lambda c: (-c[0], c[1]))
    out = []
    for _, idx in cols:
        h = "%02x%02x%02x" % tuple(pal[idx * 3:idx * 3 + 3])
        if _is_chromatic(h):
            out.append(h)
    return out


def _logo_hard_to_see(im: Any, bg: str) -> bool:
    """True when the logo's visible pixels (mean luminance) hardly differ from the background."""
    small = im.copy()
    small.thumbnail((64, 64))
    lums = [luminance("#%02x%02x%02x" % p[:3]) for p in small.getdata() if p[3] >= 128]
    if not lums:
        return False
    mean = sum(lums) / len(lums)
    lb = luminance(bg)
    return (max(mean, lb) + 0.05) / (min(mean, lb) + 0.05) < LOGO_MIN_CONTRAST


# ── entry point ─────────────────────────────────────────────────────────────

def _label_from_filename(filename: str) -> str:
    base = re.split(r"[\\/]", filename or "")[-1]
    if "." in base and len(base.rsplit(".", 1)[1]) <= 5:
        base = base.rsplit(".", 1)[0]
    base = " ".join(re.sub(r"[^\w \-.()+]", " ", base).replace("_", " ").split())
    return base.strip(" .-")[:MAX_NAME].strip() or "Imported style"


def _aspect(cx: int, cy: int) -> str:
    r = cx / cy
    if abs(r - 16 / 9) < 0.02:
        return "16:9"
    if abs(r - 4 / 3) < 0.02:
        return "4:3"
    return "other"


def import_pptx(data: bytes, filename: str = "") -> ImportResult:
    if not isinstance(data, (bytes, bytearray)) or not data:
        raise PptxImportError("The file is empty.")
    data = bytes(data)
    if len(data) > MAX_UPLOAD:
        raise PptxImportError("The file is larger than 25 MB.")
    if data[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        raise PptxImportError("This is an old binary PowerPoint file (.ppt). Save it as .pptx and try again.")
    if data[:4] != b"PK\x03\x04":
        raise PptxImportError("This file is not a PowerPoint presentation.")
    pkg = _Package(data)
    if any("vbaproject" in n.casefold() for n in pkg.infos):
        raise PptxImportError("Presentations with macros are not accepted. Save a macro-free .pptx and try again.")

    ct = pkg.xml("[Content_Types].xml")
    if ct is None or not pkg.has("ppt/presentation.xml"):
        raise PptxImportError("This file is not a PowerPoint presentation.")
    main_type = ""
    for el in ct.iter():
        ctype = el.get("ContentType") or ""
        if "macroenabled" in ctype.lower() or "vbaproject" in ctype.lower():
            raise PptxImportError("Presentations with macros are not accepted. Save a macro-free .pptx and try again.")
        if el.get("PartName") == "/ppt/presentation.xml":
            main_type = ctype
    kind = "potx" if "template" in main_type.lower() else "pptx"

    pres = pkg.xml("ppt/presentation.xml")
    sz = pres.find(f"{{{P}}}sldSz") if pres is not None else None
    cx, cy = _ext_int(sz, "cx"), _ext_int(sz, "cy")
    if not (0 < cx < 10**9 and 0 < cy < 10**9):
        cx, cy = 12192000, 6858000
    aspect = _aspect(cx, cy)

    warnings: List[str] = []
    external = sum(1 for n in pkg.names("") if n.endswith(".rels") for r in pkg.rels(n[:-5].replace("_rels/", "", 1))
                   if r["external"]) if len(pkg.infos) <= MAX_ENTRIES else 0
    embedded_fonts = len([n for n in pkg.names("ppt/fonts/")])

    masters = [n for n in pkg.names("ppt/slideMasters/") if re.fullmatch(r"ppt/slideMasters/slideMaster\d+\.xml", n)][:MAX_MASTERS]
    scheme: Dict[str, str] = {}
    major = minor = ""
    scan = _Scan()
    layouts_seen = 0
    for mi, mname in enumerate(masters):
        mroot = pkg.xml(mname)
        mrels = pkg.rels(mname)
        if mi == 0:
            for r in mrels:
                if r["type"] == "theme" and r["path"] and pkg.has(r["path"]):
                    t = pkg.xml(r["path"])
                    if t is not None:
                        scheme, major, minor = read_scheme(t)
                    break
            cm = mroot.find(f"{{{P}}}clrMap") if mroot is not None else None
            if cm is not None:
                scan.clrmap = {k: v for k, v in cm.attrib.items() if k in ("bg1", "tx1", "bg2", "tx2")}
        ctx = _Ctx(dict(scheme), dict(scan.clrmap) or _Ctx({}).clrmap)
        if mroot is None:
            continue
        if mi == 0:
            scan.bg = _bg_of(mroot, ctx)
        _scan_part(pkg, mname, mroot, ctx, (cx, cy), scan, True, mrels, mname)
        for r in mrels:
            if r["type"] != "slideLayout" or not r["path"] or layouts_seen >= MAX_LAYOUTS:
                continue
            if not r["path"].startswith("ppt/slideLayouts/") or not pkg.has(r["path"]):
                continue
            layouts_seen += 1
            lroot = pkg.xml(r["path"])
            if lroot is not None:
                _scan_part(pkg, r["path"], lroot, ctx, (cx, cy), scan, False, pkg.rels(r["path"]), r["path"])

    notes_extra: List[str] = []
    # logo: best-scoring picture that decodes as a bitmap
    mark_png: Optional[bytes] = None
    logo_img = None
    ranked = sorted((p for p in scan.pics.values() if _pic_score(p)[0] >= 0), key=lambda p: (-_pic_score(p)[0], p.path))
    vector_skipped = False
    for pic in ranked[:4]:
        try:
            raw = pkg.read(pic.path, MAX_MEDIA_BYTES)
        except OverflowError:
            continue
        if raw is None:
            continue
        png, img, problem = _logo_png(raw)
        if png:
            mark_png, logo_img = png, img
            break
        if problem == "vector":
            vector_skipped = True

    # palette
    default_name = office_default_name(scheme)
    cmap = {**{"bg1": "lt1", "tx1": "dk1"}, **scan.clrmap}
    bg1 = scheme.get(cmap["bg1"], "ffffff")
    tx1 = scheme.get(cmap["tx1"], "000000")
    deck_bg = "#" + (scan.bg or bg1)
    accents_theme = ["#" + scheme[k] for k in _SCHEME_KEYS[4:] if k in scheme and _HEX6.fullmatch(scheme[k])]
    sampled: List[str] = []
    if default_name or not accents_theme:
        sampled = ["#" + c for c in (_image_colors(logo_img) if logo_img is not None else [])]
        theme_cols = set(scheme.values())
        shapes = sorted(((a, c) for c, a in scan.shape_area.items() if c not in theme_cols and _is_chromatic(c)),
                        key=lambda t: (-t[0], t[1]))
        sampled += ["#" + c for _, c in shapes]
    if default_name or not accents_theme:
        if sampled:
            accents = sampled
            warnings.append("This deck uses the default Office colours, so its theme says little about its look. "
                            "The accent colour was sampled from its logo and shapes; check it in the preview.")
        else:
            accents = [NEUTRAL_ACCENT]
            warnings.append("This deck uses the default Office colours and has no distinctive logo or shapes, "
                            "so a neutral accent colour was used. Pick your own accent in the preview.")
    else:
        accents = accents_theme

    tokens = copy.deepcopy(load_tokens())
    own_light = luminance(deck_bg) >= 0.179
    own_theme = "light" if own_light else "dark"
    other_theme = "dark" if own_light else "light"
    neutral = bool(default_name) or not scheme
    # the deck's own text colour is tx1; the derived theme uses black/white-ish text
    text_own = "#" + tx1
    accent_adjusted = False
    style: Optional[Style] = None
    last_err = ""
    base_name = _label_from_filename(filename)
    sha = hashlib.sha256(data).hexdigest()
    for attempt in range(3):
        bg_own = deck_bg
        if attempt == 1:
            bg_own = mix(deck_bg, "#ffffff" if own_light else "#000000", 0.5)
        elif attempt == 2:
            bg_own = "#ffffff" if own_light else "#15171c"
        bg_other = _other_bg(not own_light, scheme, neutral or attempt > 0)
        pal_own, adj = _palette(bg_own, text_own, accents,
                                tokens[own_theme]["success"])
        pal_other, _ = _palette(bg_other, "#f2f2f2" if own_light else "#141414", accents,
                                tokens[other_theme]["success"])
        accent_adjusted = adj
        tokens[own_theme].update(pal_own)
        tokens[other_theme].update(pal_other)
        h_fam, h_why = map_font(major)
        b_fam, b_why = map_font(minor or major)
        tokens["typography"].update(heading_family=h_fam, body_family=b_fam, mono_family="JetBrains Mono")
        tokens["source"] = "Imported style"
        fonts = []
        for src, fam, why in ((major, h_fam, h_why), (minor, b_fam, b_why)):
            entry = {"from": src or "(none)", "to": fam, "reason": why}
            if entry not in fonts:
                fonts.append(entry)
        st = Style(id="sty_00000000", name=base_name, tokens=copy.deepcopy(tokens), default_theme=own_theme,
                   wordmark="", intro_mark=mark_png is not None, credit=False, decor="minimal",
                   source=sanitize_source({"kind": kind, "sha256": sha, "deck_aspect": aspect}),
                   fonts=fonts, warnings=list(warnings), mark_png=mark_png)
        try:
            style = validate_style(st)
            if attempt:
                style.warnings.append("The slide background was adjusted so text stays readable.")
            break
        except StyleError as e:
            last_err = str(e)
    if style is None:
        raise PptxImportError("A readable style could not be built from this deck.")

    if accent_adjusted and not (default_name and accents == [NEUTRAL_ACCENT]):
        style.warnings.append("The accent colour was adjusted slightly so it stays readable on the background.")
    if logo_img is not None and mark_png is not None and _logo_hard_to_see(logo_img, style.tokens[own_theme]["bg"]):
        style.warnings.append("The logo may be hard to see on this style's background. "
                              "Check the preview, or add a logo version that suits it.")
    if aspect != "16:9":
        style.warnings.append(f"This deck is {aspect if aspect == '4:3' else 'not 16:9'}; "
                              "only its colours, fonts and logo are used.")
    if embedded_fonts:
        style.warnings.append(f"{embedded_fonts} embedded font files were not used; bundled fonts replace them.")
    if external:
        style.warnings.append(f"{external} linked external resources were ignored.")
    if vector_skipped and mark_png is None:
        style.warnings.append("A vector logo (SVG, EMF or WMF) was skipped; only bitmap logos are supported. "
                              "Add a PNG logo in the preview.")
    if pkg.names("ppt/embeddings/"):
        style.warnings.append("Embedded objects in the deck were ignored.")
    style = validate_style(style)
    return ImportResult(style=style, notes=list(style.warnings))
