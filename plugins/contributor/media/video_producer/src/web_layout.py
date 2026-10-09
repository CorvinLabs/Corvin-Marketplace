"""Layout check for rendered web slides: nothing may visually collide.

Runs inside the already-loaded slide (the same page.evaluate channel the
renderer uses for seeking) at the settled end state and measures real boxes:
every text node's rect, and every visible box (border, fill, svg rect/circle).
Reported defects:

  text-text      two text runs intersect
  text-box       text intersects a box it does not sit inside, or pokes out of the box it sits in
  box-box        two boxes intersect without one containing the other
  clipped        an overflow-hidden element is cutting its own text
  off-stage      text outside the 1920x1080 stage

Decorative layers (stars, glow, ring, ambient pulses, connector lines) are not
measured: they are meant to sit behind or between content.
"""

from typing import Any, Dict, List

TOLERANCE_PX = 2

LAYOUT_JS = r"""(tol) => {
  const W = innerWidth, H = innerHeight;
  const SKIP = '.stars, .glow, .ring, .amb, defs, script, style';
  const hidden = el => {
    for (let e = el; e && e.nodeType === 1; e = e.parentElement) {
      const cs = getComputedStyle(e);
      if (cs.display === 'none' || cs.visibility === 'hidden' || parseFloat(cs.opacity) === 0) return true;
    }
    return false;
  };
  const alpha = c => { const m = c.match(/rgba?\(([^)]+)\)/); if (!m) return 0;
    const p = m[1].split(',').map(parseFloat); return p.length > 3 ? p[3] : 1; };
  const R = r => ({x: r.left, y: r.top, w: r.width, h: r.height});
  const name = el => (el.tagName.toLowerCase() + (el.className && el.className.baseVal === undefined && el.className ? '.' + String(el.className).trim().split(/\s+/)[0] : ''));
  const texts = [], boxes = [], clipped = [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let n; (n = walker.nextNode());) {
    if (!n.data.trim()) continue;
    const el = n.parentElement;
    if (!el || el.closest(SKIP) || hidden(el)) continue;
    const rg = document.createRange(); rg.selectNodeContents(n);
    for (const line of rg.getClientRects()) {
    let rc = R(line);
    if (rc.w < 1 || rc.h < 1) continue;
    for (let a = el; a && a !== document.body; a = a.parentElement) {
      const ac = getComputedStyle(a);
      if (a.namespaceURI === 'http://www.w3.org/1999/xhtml' && (ac.overflowX !== 'visible' || ac.overflowY !== 'visible')) {
        const c = R(a.getBoundingClientRect());
        const x0 = Math.max(rc.x, c.x), y0 = Math.max(rc.y, c.y);
        const x1 = Math.min(rc.x + rc.w, c.x + c.w), y1 = Math.min(rc.y + rc.h, c.y + c.h);
        rc = {x: x0, y: y0, w: x1 - x0, h: y1 - y0};
        if (rc.w < 1 || rc.h < 1) break;
      }
    }
    if (rc.w < 1 || rc.h < 1) continue;
    texts.push({el, rect: rc, label: n.data.trim().slice(0, 28)});
    }
  }
  for (const el of document.body.querySelectorAll('*')) {
    if (el.closest(SKIP) || hidden(el)) continue;
    const inSvg = el.namespaceURI === 'http://www.w3.org/2000/svg';
    const r = el.getBoundingClientRect();
    if (r.width < 20 || r.height < 20 || (r.width >= W * .9 && r.height >= H * .9)) continue;
    const cs = getComputedStyle(el);
    let visible = false;
    if (inSvg) {
      const t = el.tagName.toLowerCase();
      visible = (t === 'rect' || t === 'circle') && cs.fill !== 'none' && alpha(cs.fill) > .05;
    } else {
      const bw = parseFloat(cs.borderTopWidth) > 0 && alpha(cs.borderTopColor) > .05;
      visible = bw || alpha(cs.backgroundColor) > .05;
    }
    if (visible) boxes.push({el, rect: R(r), label: name(el)});
    if (!inSvg && [...el.childNodes].some(c => c.nodeType === 3 && c.data.trim()) && /(hidden|clip)/.test(cs.overflowX) && el.scrollWidth > el.clientWidth + 1 && el.textContent.trim())
      clipped.push({type: 'clipped', a: name(el), b: el.textContent.trim().slice(0, 28)});
  }
  const inter = (a, b) => {
    const x = Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x);
    const y = Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y);
    return x > tol && y > tol ? [x, y] : null;
  };
  const inside = (a, b) => a.x >= b.x - tol && a.y >= b.y - tol && a.x + a.w <= b.x + b.w + tol && a.y + a.h <= b.y + b.h + tol;
  const out = [...clipped];
  const rep = (type, a, b, rect) => out.push({type, a: a.label, b: b.label, at: [Math.round(rect.x), Math.round(rect.y)]});
  for (let i = 0; i < texts.length; i++) {
    const t = texts[i];
    if (t.rect.x < -tol || t.rect.y < -tol || t.rect.x + t.rect.w > W + tol || t.rect.y + t.rect.h > H + tol)
      out.push({type: 'off-stage', a: t.label, b: '', at: [Math.round(t.rect.x), Math.round(t.rect.y)]});
    for (let j = i + 1; j < texts.length; j++) {
      const o = texts[j], ov = inter(t.rect, o.rect);
      if (!ov) continue;
      const sameLine = ov[1] >= .6 * Math.min(t.rect.h, o.rect.h);
      if (t.el === o.el || (sameLine && ov[0] < 6)) continue;  // runs of one element, or glyphs touching on a line
      rep('text-text', t, o, t.rect);
    }
    for (const b of boxes) {
      const own = b.el.contains(t.el) || (b.el.namespaceURI !== 'http://www.w3.org/1999/xhtml' && b.el.parentElement.contains(t.el));
      if (own ? !inside(t.rect, b.rect) : inter(t.rect, b.rect)) rep('text-box', t, b, t.rect);
    }
  }
  for (let i = 0; i < boxes.length; i++) for (let j = i + 1; j < boxes.length; j++) {
    const a = boxes[i], b = boxes[j];
    if (a.el.contains(b.el) || b.el.contains(a.el)) continue;
    if (inter(a.rect, b.rect) && !inside(a.rect, b.rect) && !inside(b.rect, a.rect)) rep('box-box', a, b, a.rect);
  }
  return out.slice(0, 30);
}"""


def format_issues(issues: List[Dict[str, Any]]) -> List[str]:
    return [f"{i['type']}: {i['a']} / {i['b']} @ {i.get('at')}" if i.get("b") or i.get("at") else f"{i['type']}: {i['a']}"
            for i in issues]
