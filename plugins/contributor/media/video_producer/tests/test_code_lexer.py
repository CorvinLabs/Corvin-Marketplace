"""code_fidelity - the gate of ADR-2249 spike S4 / task T-0106.

For ANY input, the lexer's token texts joined equal the input byte for byte. Checked on the raw scan
(``scan``, no safety net - a bug must fail HERE, not be hidden by the fallback in ``tokenize``) over
>= 500 real stdlib files, fragments cut from them at random offsets, a fuzz corpus of the shapes that
break lexers, and hostile inputs that must cost linear time.
"""
import random
import sysconfig
import time
from pathlib import Path

import pytest

from src import code_lexer as L

STDLIB = Path(sysconfig.get_paths()["stdlib"])
SEED = 20261010


def _py_files(limit=None):
    files = sorted(p for p in STDLIB.rglob("*.py") if "site-packages" not in p.parts and p.stat().st_size < 400_000)
    return files if limit is None else files[:limit]


def _check(text, lang):
    toks = L.scan(text, lang)
    assert "".join(t for _, t in toks) == text, (lang, text[:80])
    assert all(t for _, t in toks), "empty token"
    assert {k for k, _ in toks} <= L.KINDS
    rows = L.lines(toks)
    assert "\n".join("".join(t for _, t in row) for row in rows) == text


def test_corpus_is_big_enough_to_mean_something():
    assert len(_py_files()) >= 500, "the stdlib corpus of this host is smaller than the gate requires"


def test_whole_stdlib_files_roundtrip_exactly():
    n = 0
    for p in _py_files():
        text = p.read_bytes().decode("utf-8", "replace")
        _check(text, "python")
        n += 1
    assert n >= 500


def test_fragments_cut_at_random_offsets_roundtrip_exactly():
    rng = random.Random(SEED)
    files = _py_files()
    for _ in range(3000):
        text = rng.choice(files).read_bytes().decode("utf-8", "replace")
        a = rng.randrange(0, max(1, len(text)))
        b = min(len(text), a + rng.choice((1, 3, 17, 80, 400, 2000)))
        _check(text[a:b], "python")  # cut mid-string, mid-escape, mid-triple-quote, mid-line


_ALPHABET = list("\"'`\\\n\r\t {}[]()<>=:#$%&*-+/.,;@!?~^|_0123456789abcXYZ") + ["\"\"\"", "'''", "\\\n", "\x00", "\x0b",
                                                                              "é", "日", "\u00a0", "\U0001f600", "f\"", "rb'", "0x", "1e", "--", "$(", "${", "- ", ": "]


@pytest.mark.parametrize("lang", L.LANGS)
def test_fuzz_roundtrip_every_language(lang):
    rng = random.Random(SEED + hash(lang) % 1000)
    for _ in range(4000):
        text = "".join(rng.choice(_ALPHABET) for _ in range(rng.randrange(0, 160)))
        _check(text, lang)


@pytest.mark.parametrize("lang", L.LANGS)
def test_real_non_python_samples_roundtrip(lang):
    samples = {
        "shell": ["#!/bin/sh\nset -eu\nfor f in *.txt; do echo \"$f\" | grep -q 'x' && cat \"${f}\" ; done\n$ ls -la /tmp\n"],
        "json": ['{"a": [1, 2.5e3, true, null], "b": {"c": "d\\"e"}}\n', '{"unterminated": "abc\n'],
        "yaml": ["a: 1\nb:\n  - x: &anchor y\n  - *anchor\nc: 'it''s' # note\n", "---\nkey: |\n  literal\n"],
        "python": ["x = '''abc", "def f(:\n  pass\n\t\x00", "ünï = 'çödé'\n"],
        "text": ["# a comment\nplain line\n// other\n"],
    }
    for text in samples[lang]:
        _check(text, lang)


def test_empty_and_single_characters():
    for lang in L.LANGS:
        _check("", lang)
        for ch in "\n \t\"'\\#$-:{@0.é\x00":
            _check(ch, lang)


def test_unknown_language_is_text_and_says_so():
    assert L.resolve_lang("rust") == "text" and L.resolve_lang(None) == "text"
    assert L.resolve_lang("Py") == "python" and L.resolve_lang("bash") == "shell" and L.resolve_lang("YML") == "yaml"


def test_tokenize_never_returns_altered_text_even_if_a_scan_were_wrong(monkeypatch):
    monkeypatch.setitem(L._LEXERS, "python", lambda text: [("name", text[:-1])])  # a lexer that drops a character
    assert L.tokenize("abc", "python") == [("text", "abc")]
    monkeypatch.setitem(L._LEXERS, "python", lambda text: [("bogus", text)])
    assert L.tokenize("abc", "python") == [("text", "abc")]


def test_output_is_deterministic_and_independent_of_the_python_version():
    text = _py_files()[0].read_text(errors="replace")
    assert L.scan(text, "python") == L.scan(text, "python")
    src = Path(L.__file__).read_text()
    # the keyword list is fixed in the module: keyword.kwlist changes between Python versions
    assert "import keyword" not in src and "keyword.kwlist" not in src.replace("``keyword.kwlist``", "")


def test_semantic_spot_checks():
    kinds = {t: k for k, t in L.tokenize("def f(x):  # c\n    return 'a' + 0x1F\n", "python") if k != "ws"}
    assert kinds["def"] == "keyword" and kinds["# c"] == "comment" and kinds["'a'"] == "string" and kinds["0x1F"] == "number"
    assert dict((t, k) for k, t in L.tokenize('{"a": "b"}', "json"))['"a"'] == "key"
    assert dict((t, k) for k, t in L.tokenize('{"a": "b"}', "json"))['"b"'] == "string"


@pytest.mark.parametrize("name,text", [
    ("quotes", '"' * 200_000),
    ("single quotes", "'" * 200_000),
    ("backslashes", "\\" * 400_000),
    ("triple openers", '"""' * 70_000),
    ("unterminated fstring", 'f"' + "{" * 150_000),
    ("digits", "1" * 300_000),
    ("dots and underscores", "1_" * 100_000 + "." * 100_000),
    ("deep brackets", "(" * 300_000),
    ("long line of names", "a " * 150_000),
    ("comment hashes", "# " * 150_000),
])
@pytest.mark.parametrize("lang", L.LANGS)
def test_hostile_input_costs_linear_time(name, text, lang):
    t0 = time.perf_counter()
    toks = L.scan(text, lang)
    elapsed = time.perf_counter() - t0
    assert "".join(t for _, t in toks) == text
    # 2 s for ~400 kB leaves a 20x margin over the ~0.1 s measured; a quadratic scan would take minutes
    assert elapsed < 2.0, (name, lang, round(elapsed, 2))
