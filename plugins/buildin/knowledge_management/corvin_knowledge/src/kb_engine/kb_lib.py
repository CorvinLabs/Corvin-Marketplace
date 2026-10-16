"""Shared primitives for the Corvin-Knowledge KB tooling (docs/CONCEPT.md, docs/MIGRATION.md).

One implementation of: frontmatter parsing, minimal line-based frontmatter edits,
ADR discovery (with the ADR-2108 positive control), deterministic ULIDs, git birth
times that follow renames, and the ADR-2108 status vocabulary/mapping.

Design rules (load-bearing):
- Frontmatter is edited LINE-BASED, never re-dumped through yaml. A yaml.dump
  round-trip would reorder keys and reflow every one of ~1000 files, turning a
  metadata migration into an unreviewable rewrite of the decision record.
- A uid is derived deterministically (birth time + path + id) so that a re-run of
  `plan` proposes the same uid; once written into a file it is never recomputed.
- Absence is never trusted without the positive control (ADR-2108 §4).
"""
from __future__ import annotations

import hashlib
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import yaml

# --- ADR-2108 schema --------------------------------------------------------------

REQUIRED = ["id", "status", "depends_on", "paths", "docs", "commits"]
LIST_FIELDS = ["depends_on", "supersedes", "related", "paths", "docs", "commits"]
VALID_STATUS = {"proposed", "accepted", "superseded", "frozen", "rejected"}

# ADR-2108 Decision §2 — verbatim mapping. `None` = map to proposed AND queue for
# verification (never guessed).
STATUS_MAP = {
    "proposed": "proposed",
    "accepted": "accepted",
    "superseded": "superseded",
    "frozen": "frozen",
    "rejected": "rejected",
    "implemented": "accepted",
    "complete": "accepted",
    "completed": "accepted",
    "decided": "accepted",
    "phase_1_complete": "accepted",
    "amended": "accepted",
    "unknown": None,
    "in_progress": None,
    "validation_phase": None,
}

CANON_NAME = re.compile(r"^ADR-(\d{4})-[a-z0-9]+(?:-[a-z0-9]+)*\.md$")
NUM_NAME = re.compile(r"^(?:ADR-)?(\d{4})[-_]")
# Matched as substrings so the control survives the Phase G rename (0264-… -> ADR-0264-…).
POSITIVE_CONTROL = ["0264-adr-decision-graph-hermeneutic-traversal.md", "ADR-0314-"]
ID_RE = re.compile(r"(\d{3,4})")
ULID_RE = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")
# a former identity: a number, or an out-of-corpus id like ADR-MESH-002
FORMER_ID_RE = re.compile(r"^ADR-(?:\d{3,4}|MESH-\d{3})$")
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def norm_id(v) -> str | None:
    m = ID_RE.search(str(v))
    return f"ADR-{int(m.group(1)):04d}" if m else None


def num_of(adr_id: str) -> int:
    return int(adr_id[4:])


# --- ULID -------------------------------------------------------------------------

def ulid(ms: int, entropy_seed: str) -> str:
    """Crockford-base32 ULID: 48-bit ms timestamp + 80 bits from sha256(seed)."""
    rnd = int.from_bytes(hashlib.sha256(entropy_seed.encode()).digest()[:10], "big")
    n = ((ms & ((1 << 48) - 1)) << 80) | rnd
    out = []
    for _ in range(26):
        out.append(_CROCKFORD[n & 31])
        n >>= 5
    return "".join(reversed(out))


# --- frontmatter ------------------------------------------------------------------

@dataclass
class Doc:
    path: Path
    text: str                  # BOM stripped, newlines normalised to "\n"
    fm: dict | None
    fm_err: str | None
    fm_start: int = 0          # line index of first frontmatter line (after '---')
    fm_end: int = 0            # line index of closing '---'
    newline: str = "\n"        # the file's own line ending, restored by write_doc()
    bom: bool = False          # the file started with a UTF-8 BOM, restored by write_doc()
    mixed: bool = False        # CRLF and bare LF both occur: no single ending to restore

    @property
    def lines(self) -> list[str]:
        return self.text.split("\n")


def parse(path: Path) -> Doc:
    """Read a KB file without losing anything a writer would put back: a UTF-8 BOM and
    CRLF line endings are recorded (write_doc restores them); bytes that are not UTF-8
    make the file read-only to every writer (`not_utf8`) instead of being replaced by
    U+FFFD on the next write (adversarial review 2026-10-03, KB-core #1/#12)."""
    raw = path.read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    try:
        text = raw[3 if bom else 0:].decode("utf-8")
    except UnicodeDecodeError:
        return Doc(path, raw.decode("utf-8", errors="replace"), None, "not_utf8")
    newline = "\r\n" if "\r\n" in text else "\n"
    mixed = newline == "\r\n" and "\n" in text.replace("\r\n", "")
    text = text.replace("\r\n", "\n")
    if mixed:   # read-only to writers: rewriting would turn every LF line into CRLF
        return Doc(path, text, None, "mixed_line_endings", newline=newline, bom=bom, mixed=True)
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        # text before a frontmatter block is a judgement (whose header is it?), never a
        # file that merely lacks one — heal must not prepend a second header to it
        err = "text_before_frontmatter" if text.lstrip().startswith("---") else "no_frontmatter"
        return Doc(path, text, None, err, newline=newline, bom=bom)
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            raw_fm = "\n".join(lines[1:i])
            try:
                fm = yaml.safe_load(raw_fm) or {}
            except yaml.YAMLError as e:
                return Doc(path, text, None, f"yaml_error: {str(e).splitlines()[0]}", 1, i, newline, bom)
            if not isinstance(fm, dict):
                return Doc(path, text, None, "frontmatter_not_mapping", 1, i, newline, bom)
            return Doc(path, text, fm, None, 1, i, newline, bom)
    return Doc(path, text, None, "unterminated_frontmatter", newline=newline, bom=bom)


def write_doc(path: Path, text: str, like: Doc | None = None) -> None:
    """Write `text` (\n-normalised) atomically, restoring the original BOM and line
    ending, and NEVER through a symlink: a link planted in a pulled KB would otherwise
    let `kb heal` (run by the console) write outside the repository (review S-#2)."""
    if path.is_symlink():
        raise SystemExit(f"refused: {path} is a symlink — the KB never writes through one")
    if like is not None and like.mixed:
        raise SystemExit(f"refused: {path} mixes CRLF and LF line endings — normalise it by hand")
    nl, bom = (like.newline, like.bom) if like else ("\n", False)
    data = (("\ufeff" if bom else "") + text.replace("\n", nl)).encode("utf-8")
    import os
    import tempfile
    fd, tmp = tempfile.mkstemp(prefix=".kbw-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.chmod(tmp, path.stat().st_mode & 0o777 if path.exists() else 0o644)   # mkstemp is 0600
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


_TOP_KEY = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*)\s*:(.*)$")  # Space vor : ist valid YAML


def _continues(lines: list[str], j: int, end: int) -> bool:
    ln = lines[j]
    if ln.startswith((" ", "\t", "- ")) or ln == "-":
        return True
    if ln.strip() and not ln.startswith("#") and not _TOP_KEY.match(ln):
        return True   # a column-0 continuation of a quoted/plain multi-line scalar
    if ln.strip() == "":
        # a blank line inside a block scalar belongs to the value; one before the next
        # top-level key does not (review KB-core #3: the span used to stop at the first
        # blank line and left the rest of a multi-line value orphaned)
        k = j + 1
        while k < end and lines[k].strip() == "":
            k += 1
        return k < end and (lines[k].startswith((" ", "\t"))
                            or (not lines[k].startswith("#") and not _TOP_KEY.match(lines[k])))
    return False


def _key_span(lines: list[str], start: int, end: int, key: str) -> tuple[int, int] | None:
    """[i, j) line span of a top-level key including its indented/list continuation."""
    for i in range(start, end):
        m = _TOP_KEY.match(lines[i])
        if m and m.group(1) == key:
            j = i + 1
            while j < end and _continues(lines, j, end):
                j += 1
            return i, j
    return None


def fm_set(text: str, key: str, value_yaml: str, after: str = "id") -> str:
    """Set top-level `key: value_yaml` (value_yaml already YAML-rendered, may be
    multi-line starting with '\\n'). Replaces the key's whole span if present,
    else inserts right after the `after` key (or at the top)."""
    d = _doc_from_text(text)
    lines = d.lines
    new = f"{key}: {value_yaml}" if not value_yaml.startswith("\n") else f"{key}:{value_yaml}"
    span = _key_span(lines, d.fm_start, d.fm_end, key)
    if span:
        lines[span[0]:span[1]] = new.split("\n")
    else:
        anchor = _key_span(lines, d.fm_start, d.fm_end, after)
        at = anchor[1] if anchor else d.fm_start
        lines[at:at] = new.split("\n")
    return "\n".join(lines)


def fm_remove(text: str, key: str) -> str:
    d = _doc_from_text(text)
    lines = d.lines
    span = _key_span(lines, d.fm_start, d.fm_end, key)
    if span:
        del lines[span[0]:span[1]]
    return "\n".join(lines)


def _doc_from_text(text: str) -> Doc:
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        raise ValueError("no frontmatter")
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return Doc(Path("<mem>"), text, None, None, 1, i)
    raise ValueError("unterminated frontmatter")


def as_list(v) -> list[str]:
    """A frontmatter list field as a list of strings, whatever was written by hand
    (`labels: urgent`, `renumbered_from: 12`) — readers never iterate a str by
    character or crash on an int (review KB-core #9)."""
    if v is None:
        return []
    if isinstance(v, (list, tuple)):
        return [str(x) for x in v if x is not None and str(x) != ""]
    return [str(v)]


def yaml_list(items: list[str]) -> str:
    return "[]" if not items else "\n" + "\n".join(f"- {x}" for x in items)


# --- discovery --------------------------------------------------------------------

@dataclass
class Adr:
    path: Path
    name: str
    num: str | None            # ADR-NNNN from filename
    doc: Doc
    born: int = 0              # unix seconds of first add (follows renames)
    meta: dict = field(default_factory=dict)

    @property
    def fm(self) -> dict:
        return self.doc.fm or {}

    @property
    def slug(self) -> str:
        return re.sub(r"^(?:ADR-|adr_)?\d{4}[-_]", "", self.name)[:-3]


def discover(dec: Path, *, positive_control: bool = True) -> list[Adr]:
    files = sorted(p for p in dec.iterdir() if p.is_file() and p.suffix == ".md")
    if positive_control:
        names = [p.name for p in files]
        missing = [n for n in POSITIVE_CONTROL if not any(n in x for x in names)]
        if missing:
            raise SystemExit(f"POSITIVE CONTROL FAILED: {missing} not found in {dec} — "
                             "refusing to trust any absence finding from this scan")
    out = []
    for p in files:
        m = NUM_NAME.match(p.name)
        out.append(Adr(p, p.name, f"ADR-{int(m.group(1)):04d}" if m else None, parse(p)))
    return out


def git(repo: Path, *args: str, check: bool = True) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed in {repo}: {r.stderr.strip()}")
    return r.stdout


def birth_times(repo: Path, subdir: str = "decisions", with_commit: bool = False):
    """Map current repo-relative path -> unix time of first add, following renames.
    One oldest-first `git log --name-status -M` pass instead of N `--follow` calls.
    with_commit=True returns (born, born_commit) — the sha that first added the file."""
    out = git(repo, "log", "--reverse", "--format=C %at %H", "--name-status", "-M", "--", subdir)
    born: dict[str, int] = {}
    bc: dict[str, str] = {}
    hist: dict[str, list[str]] = {}
    t, sha = 0, ""
    for line in out.splitlines():
        if line.startswith("C "):
            _, ts, sha = line.split(" ")
            t = int(ts)
            continue
        parts = line.split("\t")
        if not parts or not parts[0]:
            continue
        st = parts[0][0]
        if st == "A":
            if parts[1] not in born:
                born[parts[1]], bc[parts[1]] = t, sha
        elif st in ("R", "C") and len(parts) == 3:
            old, new = parts[1], parts[2]
            born[new] = born.get(old, t) if st == "R" else t
            bc[new] = bc.get(old, sha) if st == "R" else sha
            if st == "R":
                hist[new] = hist.pop(old, []) + [old]
                born.pop(old, None)
                bc.pop(old, None)
        elif st == "D":
            born.pop(parts[1], None)
            bc.pop(parts[1], None)
    if with_commit:
        return born, bc, {k: v for k, v in hist.items() if k in born}
    return born


_EMBEDDED = re.compile(r"^ADR-\d{4}-(\d{4})[-_]")


def former_ids(a: "Adr", target: str, history: list[str] | None = None) -> set[str]:
    """Every id this decision has been cited under, other than its target id:
    frontmatter id, a number embedded by a half-finished rename (ADR-0809-0537-…),
    the numbers of earlier filenames (git rename history), existing renumbered_from."""
    out = set()
    fid = norm_id(a.fm.get("id")) if a.fm.get("id") is not None else None
    if fid:
        out.add(fid)
    if a.num:
        out.add(a.num)
    m = _EMBEDDED.match(a.name)
    if m:
        out.add(f"ADR-{int(m.group(1)):04d}")
    for old in history or []:
        mm = NUM_NAME.match(old.rsplit("/", 1)[-1])
        if mm:
            out.add(f"ADR-{int(mm.group(1)):04d}")
    rf = a.fm.get("renumbered_from")
    for x in (rf if isinstance(rf, list) else [rf] if rf else []):
        if FORMER_ID_RE.match(str(x)):
            out.add(str(x))
    out.discard(target)
    return out


def kebab(s: str) -> str:
    s = s.lower().replace("_", "-")
    s = re.sub(r"[^a-z0-9-]+", "-", s)
    return re.sub(r"-{2,}", "-", s).strip("-") or "untitled"


def slug_words(s: str) -> set[str]:
    # generic architecture vocabulary carries no signal for telling two ADRs apart
    stop = {"adr", "the", "and", "for", "of", "a", "to", "in", "md", "v2", "phase", "with",
            "unified", "system", "integration", "architecture", "framework", "layer", "corvin",
            "corvinos", "design", "implementation", "support", "based", "new", "core"}
    return {w for w in re.split(r"[^a-z0-9]+", s.lower()) if len(w) > 2 and w not in stop}


def jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def fm_of(text: str) -> dict | None:
    """The frontmatter mapping of an in-memory text, or None if it is not one."""
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            try:
                fm = yaml.safe_load("\n".join(lines[1:i])) or {}
            except yaml.YAMLError:
                return None
            return fm if isinstance(fm, dict) else None
    return None


def glob_match(path: str, pat: str) -> bool:
    """THE repo-path glob both gates use (kb's sweep and adr_lint): fnmatch semantics (`*` may
    cross `/`, `[a-z]` ranges, `[!..]`), plus `**/` matching zero directories, plus a pattern
    that names a DIRECTORY of the file (review R7-A5: two matchers disagreed)."""
    import fnmatch
    pats = {pat, pat.replace("**/", "")}
    cands = [path] + [path[:i] for i in range(len(path)) if path[i] == "/"]
    return any(fnmatch.fnmatchcase(c, p) for p in pats for c in cands)
