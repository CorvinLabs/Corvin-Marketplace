"""The shareable result of a tour: a self-contained page, chapters, captions and a zip (CONCEPT-0139 section 8).

Everything that came from the page or from the model is data: it goes into the HTML only through ``html.escape`` (or as
JSON in a non-executing block). The page makes no external request and carries a CSP meta whose ``script-src`` holds the
hash of its one inline script, so the folder can be uploaded to any static host as it is.
"""
from __future__ import annotations

import base64
import hashlib
import html
import json
import re
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Sequence

MAX_CUE_CHARS = 84


def _ts(t: float) -> str:
    t = max(0.0, t)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h):02d}:{int(m):02d}:{s:06.3f}"


def chapters_vtt(chapters: Sequence[Dict[str, Any]]) -> str:
    out = ["WEBVTT", ""]
    for i, c in enumerate(chapters, 1):
        out += [str(i), f"{_ts(c['start'])} --> {_ts(c['end'])}", c["title"].replace("-->", "->"), ""]
    return "\n".join(out)


def _chunks(text: str) -> List[str]:
    if len(text) <= MAX_CUE_CHARS:
        return [text]
    parts = re.split(r"(?<=[:;,.])\s+", text)
    out: List[str] = []
    cur = ""
    for p in parts:
        if cur and len(cur) + 1 + len(p) > MAX_CUE_CHARS:
            out.append(cur)
            cur = p
        else:
            cur = (cur + " " + p).strip()
    if cur:
        out.append(cur)
    return out


def captions_vtt(cues: Sequence[Dict[str, Any]]) -> str:
    out = ["WEBVTT", ""]
    n = 0
    for c in cues:
        parts = _chunks(c["text"])
        total = sum(len(p) for p in parts) or 1
        t = c["at"]
        for p in parts:
            d = c["dur"] * len(p) / total
            n += 1
            out += [str(n), f"{_ts(t)} --> {_ts(t + d)}", p.replace("-->", "->"), ""]
            t += d
    return "\n".join(out)


_LABEL = {"en": {"chapters": "Chapters", "transcript": "Transcript", "language": "Language", "play": "Play", "captions": "Captions"},
          "de": {"chapters": "Kapitel", "transcript": "Transkript", "language": "Sprache", "play": "Abspielen", "captions": "Untertitel"}}

_SCRIPT = r"""
(function () {
  var data = JSON.parse(document.getElementById('tour-data').textContent);
  var v = document.getElementById('v'), lang = data.langs[0];
  function setLang(l, keep) {
    var t = v.currentTime, paused = v.paused; lang = l;
    v.src = data.videos[l]; v.load();
    var tr = v.querySelectorAll('track'); for (var i = 0; i < tr.length; i++) tr[i].remove();
    ['chapters', 'captions'].forEach(function (kind) { var e = document.createElement('track'); e.kind = kind; e.srclang = l;
      e.label = data.labels[l][kind]; e.src = data.tracks[l][kind]; if (kind === 'chapters') e.default = true; v.appendChild(e); });
    v.addEventListener('loadedmetadata', function once() { v.removeEventListener('loadedmetadata', once);
      if (keep) { v.currentTime = t; if (!paused) v.play(); } });
    document.querySelectorAll('[data-lang]').forEach(function (b) { b.setAttribute('aria-pressed', b.getAttribute('data-lang') === l ? 'true' : 'false'); });
    document.querySelectorAll('[data-tr]').forEach(function (d) { d.hidden = d.getAttribute('data-tr') !== l; });
    document.documentElement.lang = l;
  }
  document.querySelectorAll('[data-lang]').forEach(function (b) { b.addEventListener('click', function () { setLang(b.getAttribute('data-lang'), true); }); });
  document.querySelectorAll('[data-t]').forEach(function (b) { b.addEventListener('click', function () { v.currentTime = parseFloat(b.getAttribute('data-t')); v.play(); }); });
  v.addEventListener('timeupdate', function () { var t = v.currentTime, cur = -1;
    data.chapters.forEach(function (c, i) { if (t >= c.start) cur = i; });
    document.querySelectorAll('[data-t]').forEach(function (b, i) { b.classList.toggle('on', i === cur); }); });
  setLang(lang, false);
})();
"""

_CSS = """
:root{color-scheme:dark light;--bg:#0b0e13;--fg:#e9eef4;--mut:#93a0b0;--card:#12161d;--line:#242c37;--acc:#e9b667}
@media (prefers-color-scheme:light){:root{--bg:#f6f7f9;--fg:#111827;--mut:#4b5563;--card:#fff;--line:#d8dde5;--acc:#b45309}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.6 system-ui,-apple-system,'Segoe UI',Roboto,sans-serif}
main{max-width:1080px;margin:0 auto;padding:28px 20px 60px}h1{font:400 clamp(1.6rem,3.4vw,2.4rem)/1.15 Georgia,'Times New Roman',serif;margin:0 0 6px}
p.sub{color:var(--mut);margin:0 0 20px}.frame{border-radius:14px;overflow:hidden;border:1px solid var(--line);background:#000}
video{display:block;width:100%;height:auto;aspect-ratio:16/9;background:#000}
.bar{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin:14px 0}.bar button,.chap button{font:inherit;color:var(--fg);background:var(--card);
border:1px solid var(--line);border-radius:999px;padding:8px 14px;cursor:pointer}.bar button[aria-pressed=true]{border-color:var(--acc);color:var(--acc)}
.chap{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:10px;margin:8px 0 22px}.chap button{border-radius:12px;text-align:left;padding:10px 14px}
.chap button.on{border-color:var(--acc)}.chap small{display:block;color:var(--mut)}h2{font-size:1.05rem;margin:22px 0 8px}
details{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:10px 16px}summary{cursor:pointer}details p{margin:.5em 0;color:var(--mut)}
footer{color:var(--mut);font-size:.85rem;margin-top:30px}button:focus-visible,summary:focus-visible{outline:2px solid var(--acc);outline-offset:2px}
"""


def build_site(site: Path, *, title: str, description: str, langs: Sequence[str], videos: Dict[str, str], chapters: Sequence[Dict[str, Any]],
               transcript: Dict[str, List[str]], disclosure: Dict[str, str], source_url: str = "") -> str:
    """Write ``site/index.html`` (the media files and the tracks are written by the caller); returns the CSP string."""
    labels = {lg: _LABEL[lg] for lg in langs}
    data = {"langs": list(langs), "videos": videos, "labels": labels, "chapters": [{"start": c["start"], "title": c["title"]} for c in chapters],
            "tracks": {lg: {"chapters": f"chapters.{lg}.vtt", "captions": f"captions.{lg}.vtt"} for lg in langs}}
    esc = html.escape
    # "</" must never end the data block early
    data_json = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    script_hash = base64.b64encode(hashlib.sha256(_SCRIPT.encode("utf-8")).digest()).decode("ascii")
    csp = f"default-src 'none'; media-src 'self'; img-src 'self'; style-src 'unsafe-inline'; script-src 'sha256-{script_hash}'; base-uri 'none'; form-action 'none'"
    lang_buttons = "".join(f'<button type="button" data-lang="{esc(lg)}" aria-pressed="false">{esc(lg.upper())}</button>' for lg in langs) if len(langs) > 1 else ""
    chap = "".join(f'<button type="button" data-t="{c["start"]:.2f}">{esc(c["title"])}<small>{_ts(c["start"])[3:8]}</small></button>' for c in chapters)
    tr = "".join(f'<div data-tr="{esc(lg)}" hidden>{"".join(f"<p>{esc(s)}</p>" for s in transcript[lg])}<p><small>{esc(disclosure[lg])}</small></p></div>' for lg in langs)
    source = f'<p class="sub"><small>{esc(source_url)}</small></p>' if source_url else ""
    first = langs[0]
    page = f"""<!doctype html>
<html lang="{esc(first)}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="{esc(csp)}">
<title>{esc(title)}</title><meta name="description" content="{esc(description)}">
<meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(description)}"><meta property="og:type" content="video.other">
<style>{_CSS}</style></head><body><main>
<h1>{esc(title)}</h1><p class="sub">{esc(description)}</p>
<div class="frame"><video id="v" controls preload="metadata" poster="poster.jpg" playsinline></video></div>
<div class="bar">{lang_buttons}</div>
<h2>{esc(labels[first]['chapters'])}</h2><div class="chap">{chap}</div>
<h2>{esc(labels[first]['transcript'])}</h2><details><summary>{esc(labels[first]['transcript'])}</summary>{tr}</details>
{source}<footer>CorvinTV website tour</footer>
</main><script type="application/json" id="tour-data">{data_json}</script><script>{_SCRIPT}</script></body></html>
"""
    (site / "index.html").write_text(page, encoding="utf-8")
    return csp


README = """Website tour bundle
===================

This folder is a complete web page. To put it online, upload the WHOLE folder to any static web host
(your own server, GitHub Pages, Netlify, Cloudflare Pages) and open index.html.
To send it, use website-bundle.zip and tell the receiver to unzip it and open index.html.

Files
- index.html          the page (player, chapters, transcript); makes no request to any other site
- video.<lang>.mp4    the video, one file per language
- poster.jpg          the still shown before play
- chapters.<lang>.vtt, captions.<lang>.vtt   chapter and caption tracks (captions are off until the viewer turns them on)

Sharing on social networks needs an absolute address for the preview image; add it to the og:image tag after you know the URL.
The narration voice is AI-generated; the page says so in the transcript.
"""


def write_zip(site: Path, out: Path) -> None:
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(site.rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(site).as_posix())
