"""Page-side effects and the maths that drives them (CONCEPT-0139 section 6).

The browser draws; this module decides. Every effect is a pure function of the video time ``T`` (never of a real clock),
uses only ``transform``/``opacity`` or a fixed overlay, and can be switched off:

* ``spot``     the page outside the focused element is dimmed (up to 55 %), with a soft ring, eased in and out;
* ``reveal``   the page's own reveal markers (``[data-reveal]``, ``[data-aos]``, ``.reveal``) rise into place as they
               enter the lower part of the picture, a function of the camera position (so it follows the camera);
* ``zoom``     a slow push-in (1.0 -> 1.035) that continues from scene to scene (done by the cropper, not the page);
* ``vignette`` a fixed soft edge darkening;
* cards        the intro (two lines) and the end card, in the page's own colours.
"""
from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .camera import Pchip

REVEAL_SELECTOR = "[data-reveal],[data-aos],.reveal"
ZOOM_MAX = 1.035
SPOT_MAX = 0.55
SPOT_IN_S, SPOT_OUT_S = 0.5, 0.5
VEIL_FADE_S = 0.7
END_FADE_S = 0.5

DEFAULTS: Dict[str, bool] = {"spot": True, "reveal": True, "zoom": True, "vignette": True}


def smooth(x: float) -> float:
    x = 0.0 if x < 0 else 1.0 if x > 1 else x
    return x * x * (3 - 2 * x)


def clean_effects(raw: Any) -> Dict[str, bool]:
    out = dict(DEFAULTS)
    if isinstance(raw, dict):
        for k in DEFAULTS:
            if k in raw:
                out[k] = bool(raw[k])
    return out


def zoom_curve(scene_bounds: Sequence[float], enabled: bool) -> Optional[Pchip]:
    """One continuous zoom: it pushes in over a scene and eases back out over the next, so there is never a jump at a
    scene boundary. ``scene_bounds`` = start times of the scenes plus the total at the end."""
    if not enabled or len(scene_bounds) < 2:
        return None
    xs = [float(b) for b in scene_bounds]
    ys = [1.0 if i % 2 == 0 else ZOOM_MAX for i in range(len(xs))]
    return Pchip(xs, ys)


def spot_level(T: float, windows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """The active spot ``{"key", "k"}`` at time T from windows ``{"key","a","b"}`` (a..b = held time)."""
    best: Dict[str, Any] = {"key": None, "k": 0.0}
    for w in windows:
        k = smooth((T - (w["a"] - SPOT_IN_S)) / SPOT_IN_S) * (1.0 - smooth((T - w["b"]) / SPOT_OUT_S))
        if k > best["k"]:
            best = {"key": w["key"], "k": round(k, 4)}
    return best


def card_state(T: float, intro: Dict[str, float], outro: Dict[str, float]) -> Dict[str, Any]:
    """The card layers at T. ``intro`` = {"end": time the veil is gone, "line2_at": time of the second line};
    ``outro`` = {"start": time the end card starts to fade in}."""
    if T < intro["end"]:
        a = 1.0 if T < intro["end"] - VEIL_FADE_S else 1.0 - smooth((T - (intro["end"] - VEIL_FADE_S)) / VEIL_FADE_S)
        return {"kind": "intro", "a": round(a, 4), "a1": round(smooth(T / 0.5), 4), "a2": round(smooth((T - intro["line2_at"]) / 0.5), 4), "a3": 0.0}
    if T >= outro["start"]:
        a = smooth((T - outro["start"]) / END_FADE_S)
        return {"kind": "outro", "a": round(a, 4), "a1": round(a, 4), "a2": round(smooth((T - outro["start"] - 0.3) / 0.5), 4),
                "a3": round(smooth((T - outro["start"] - 0.6) / 0.5), 4)}
    return {"kind": None, "a": 0.0, "a1": 0.0, "a2": 0.0, "a3": 0.0}


def _rgba(css: str) -> Optional[Tuple[float, float, float, float]]:
    m = re.match(r"^\s*rgba?\(([^)]*)\)\s*$", css or "")
    if not m:
        return None
    p = [x.strip() for x in m.group(1).replace("/", ",").replace(" ", ",").split(",") if x.strip()]
    try:
        v = [float(x.rstrip("%")) for x in p[:4]]
    except ValueError:
        return None
    if len(v) < 3:
        return None
    return (v[0], v[1], v[2], v[3] if len(v) > 3 else 1.0)


def _lum(c: Tuple[float, float, float, float]) -> float:
    def ch(x: float) -> float:
        x /= 255.0
        return x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4
    return 0.2126 * ch(c[0]) + 0.7152 * ch(c[1]) + 0.0722 * ch(c[2])


def contrast(a: str, b: str) -> float:
    ca, cb = _rgba(a), _rgba(b)
    if ca is None or cb is None:
        return 0.0
    la, lb = sorted((_lum(ca), _lum(cb)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def card_colours(bg: str, fg: str) -> Tuple[str, str]:
    """``(background, text)`` for the intro/end cards. Many pages set their text colour on a wrapper, not on ``body``, so
    ``body``'s colour can be the browser default black on a dark page: a text that is not readable on the page's own background
    (contrast below 4.5) is replaced by white or near-black, whichever reads."""
    c = _rgba(bg)
    if c is None or c[3] < 0.5:
        bg, c = "rgb(11,14,19)", (11.0, 14.0, 19.0, 1.0)
    if contrast(bg, fg) >= 4.5:
        return bg, fg
    return bg, ("rgb(245,247,250)" if _lum(c) < 0.4 else "rgb(17,24,39)")


SETUP_JS = r"""
(cfg) => {
  const S = window.__vt = {};
  const Z = 2147483000;
  const mk = (id, css) => { const d = document.createElement('div'); d.id = id; d.setAttribute('aria-hidden', 'true');
    d.style.cssText = css; document.documentElement.appendChild(d); return d; };
  S.vig = mk('__vt_vig', 'position:fixed;inset:0;pointer-events:none;z-index:' + Z + ';display:' + (cfg.vignette ? 'block' : 'none') +
    ';background:radial-gradient(ellipse at 50% 45%,rgba(0,0,0,0) 58%,rgba(0,0,0,.34) 100%)');
  S.spot = mk('__vt_spot', 'position:fixed;pointer-events:none;z-index:' + (Z + 1) + ';border-radius:18px;display:none');
  S.card = mk('__vt_card', 'position:fixed;inset:0;z-index:' + (Z + 2) + ';display:none;flex-direction:column;align-items:center;' +
    'justify-content:center;gap:16px;text-align:center;opacity:0;background:' + cfg.bg + ';color:' + cfg.fg +
    ';font-family:' + (cfg.font || 'system-ui,sans-serif'));
  const row = (id, css) => '<div id="' + id + '" style="max-width:78%;line-height:1.18;opacity:0;' + css + '"></div>';
  S.card.innerHTML = row('__vt_l1', 'font-size:50px') + row('__vt_l2', 'font-size:40px;font-style:italic;color:' + cfg.accent) +
    row('__vt_l3', 'font-size:26px;font-weight:600;color:' + cfg.accent) +
    '<div id="__vt_l4" style="position:absolute;bottom:34px;left:0;right:0;font-size:13px;opacity:0;color:' + cfg.fg + '99"></div>';
  S.l = [1, 2, 3, 4].map((i) => document.getElementById('__vt_l' + i));
  S.setTexts = (t) => { for (let i = 0; i < 4; i++) S.l[i].textContent = (t && t[i]) || ''; };
  // animation clocks: the deepest group that contains an animation's target decides its start time
  S.groups = (cfg.groups || []).map((g) => { const el = document.querySelector(g.sel); let d = 0; for (let n = el; n; n = n.parentElement) d++;
    return { el: el, Tg: g.Tg, shift: g.shift || 0, depth: d }; }).filter((g) => g.el);
  S.clockOf = new WeakMap();
  S.reveals = [];
  if (cfg.reveal) {
    document.querySelectorAll(cfg.revealSelector).forEach((el) => { el.style.setProperty('transform', 'none', 'important');
      el.style.setProperty('transition', 'none', 'important'); });
    document.querySelectorAll(cfg.revealSelector).forEach((el) => { const r = el.getBoundingClientRect(); S.reveals.push({ el: el, top: r.top + scrollY }); });
  }
  S.spotEl = {}; for (const k of Object.keys(cfg.spotSelectors || {})) S.spotEl[k] = document.querySelector(cfg.spotSelectors[k]);
  S.frame = (s) => new Promise((resolve) => {
    window.scrollTo(0, s.scroll);
    for (const a of document.getAnimations()) {
      if (a.constructor.name === 'CSSTransition') { try { a.finish(); } catch (e) {} continue; }
      let c = S.clockOf.get(a);
      if (c === undefined) { const t = a.effect && a.effect.target; c = null; let best = -1;
        if (t) for (const g of S.groups) if (g.el.contains(t) && g.depth >= best) { c = g; best = g.depth; }
        S.clockOf.set(a, c); }
      a.pause(); a.currentTime = 720000 + (s.T - (c ? c.Tg : 0)) * 1000 + (c ? c.shift : 0);
    }
    if (cfg.reveal) { const y = window.scrollY, vh = innerHeight;
      for (const r of S.reveals) { const p = Math.max(0, Math.min(1, (vh * 0.94 - (r.top - y)) / (vh * 0.2))); const e = p * p * (3 - 2 * p);
        r.el.style.setProperty('opacity', String(e), 'important');
        r.el.style.setProperty('transform', 'translateY(' + (16 * (1 - e)).toFixed(2) + 'px)', 'important'); } }
    const sp = s.spot, el = sp && sp.key ? S.spotEl[sp.key] : null;
    if (el && sp.k > 0.01) { const r = el.getBoundingClientRect(); const k = sp.k, st = S.spot.style;
      st.display = 'block'; st.left = (r.left - 14) + 'px'; st.top = (r.top - 14) + 'px'; st.width = (r.width + 28) + 'px'; st.height = (r.height + 28) + 'px';
      st.boxShadow = '0 0 0 3000px rgba(6,8,12,' + (cfg.spotMax * k).toFixed(3) + '),0 0 0 2px ' + cfg.accentRgba.replace('A', (0.85 * k).toFixed(3)) +
        ',0 0 44px ' + cfg.accentRgba.replace('A', (0.3 * k).toFixed(3));
    } else S.spot.style.display = 'none';
    const c = s.card;
    if (c && c.kind) { S.card.style.display = 'flex'; S.card.style.opacity = String(c.a); S.l[0].style.opacity = String(c.a1);
      S.l[1].style.opacity = String(c.a2); S.l[2].style.opacity = String(c.a3); S.l[3].style.opacity = String(c.kind === 'outro' ? c.a2 : 0); }
    else S.card.style.display = 'none';
    requestAnimationFrame(() => requestAnimationFrame(() => resolve(window.scrollY)));
  });
}
"""

ACCENT_JS = r"""
() => { const a = document.querySelector('a[href]'); const cs = a ? getComputedStyle(a).color : 'rgb(233,182,103)';
  const m = /rgba?\(([^)]+)\)/.exec(cs); const p = m ? m[1].split(',').map((x) => parseFloat(x)) : [233, 182, 103];
  return { accent: 'rgb(' + p[0] + ',' + p[1] + ',' + p[2] + ')', accentRgba: 'rgba(' + p[0] + ',' + p[1] + ',' + p[2] + ',A)' }; }
"""


def setup_config(outline: Dict[str, Any], effects: Dict[str, bool], groups: List[Dict[str, Any]],
                 spot_selectors: Dict[str, str], accent: Dict[str, str]) -> Dict[str, Any]:
    bg, fg = card_colours(outline.get("bg") or "", outline.get("fg") or "")
    return {"bg": bg, "fg": fg,
            "font": (outline.get("font") or "").replace('"', "'"), "accent": accent["accent"], "accentRgba": accent["accentRgba"],
            "vignette": effects["vignette"], "reveal": effects["reveal"], "revealSelector": REVEAL_SELECTOR,
            "groups": groups, "spotSelectors": spot_selectors, "spotMax": SPOT_MAX}
