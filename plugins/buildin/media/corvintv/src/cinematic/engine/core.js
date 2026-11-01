// CorvinTV v2 scene engine: deterministic canvas renderer. No clock, no Math.random: every frame is a pure
// function of (act spec, time t, language), so frames can be sampled in any order and in parallel.
const W = 1920, H = 1080, TAU = Math.PI * 2;
const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
const lerp = (a, b, t) => a + (b - a) * t;
const fract = (x) => x - Math.floor(x);
const EASE = {
  linear: (t) => t,
  in: (t) => t * t * t,
  out: (t) => 1 - Math.pow(1 - t, 3),
  soft: (t) => 1 - Math.pow(1 - t, 2),
  inOut: (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2),
  smooth: (t) => t * t * (3 - 2 * t),
  back: (t) => { const c1 = 1.70158, c3 = c1 + 1; return 1 + c3 * Math.pow(t - 1, 3) + c1 * Math.pow(t - 1, 2); },
  drop: (t) => { // falls, hits, one small rebound
    if (t < 0.72) return (t / 0.72) ** 2;
    const u = (t - 0.72) / 0.28; return 1 - 0.06 * Math.sin(u * Math.PI);
  },
  step: (t) => (t >= 1 ? 1 : 0),
};
function prng(seed) { let s = (seed >>> 0) || 1; return () => { s ^= s << 13; s >>>= 0; s ^= s >>> 17; s ^= s << 5; s >>>= 0; return s / 4294967296; }; }
const _col = {};
function hueHex(deg) { // a hue in degrees (0..360) at fixed saturation and lightness, as #rrggbb
  const h = ((deg % 360) + 360) % 360 / 60, s = 0.75, l = 0.65, c = (1 - Math.abs(2 * l - 1)) * s, x = c * (1 - Math.abs(h % 2 - 1)), m = l - c / 2;
  const [r, g, b] = h < 1 ? [c, x, 0] : h < 2 ? [x, c, 0] : h < 3 ? [0, c, x] : h < 4 ? [0, x, c] : h < 5 ? [x, 0, c] : [c, 0, x];
  return '#' + [r, g, b].map((v) => Math.round((v + m) * 255).toString(16).padStart(2, '0')).join('');
}
function rgb(h) {
  if (typeof h === 'number') h = hueHex(h);            // a bare number is a hue in degrees
  if (typeof h !== 'string' || !/^#?[0-9a-fA-F]{3}([0-9a-fA-F]{3})?$/.test(h.trim())) h = '#ffffff'; // anything else: neutral, never an exception
  if (_col[h]) return _col[h];
  let s = h.trim().replace('#', ''); if (s.length === 3) s = s.split('').map((x) => x + x).join('');
  const v = [parseInt(s.slice(0, 2), 16), parseInt(s.slice(2, 4), 16), parseInt(s.slice(4, 6), 16)];
  return (_col[h] = v);
}
const rgba = (h, a) => { const v = rgb(h); return `rgba(${v[0]},${v[1]},${v[2]},${clamp(a)})`; };
function mix(a, b, t) { const x = rgb(a), y = rgb(b); t = clamp(t); return '#' + [0, 1, 2].map((i) => Math.round(lerp(x[i], y[i], t)).toString(16).padStart(2, '0')).join(''); }
const PAL = {
  bg0: '#05070e', bg1: '#0b1220', ink: '#ece9e2', mute: '#8d97a8', amber: '#e8a83a', amberD: '#c4861a',
  teal: '#2ec4b6', ice: '#bfe9ff', violet: '#8b7bd8', red: '#d95d5d', green: '#56c596', blue: '#5b8def', stone: '#2a3550',
};
function glow(c, x, y, r, col, a) {
  const g = c.createRadialGradient(x, y, 0, x, y, r);
  g.addColorStop(0, rgba(col, a)); g.addColorStop(0.4, rgba(col, a * 0.35)); g.addColorStop(1, rgba(col, 0));
  c.fillStyle = g; c.beginPath(); c.arc(x, y, r, 0, TAU); c.fill();
}
function glowAdd(c, x, y, r, col, a) { c.save(); c.globalCompositeOperation = 'lighter'; glow(c, x, y, r, col, a); c.restore(); }

// ---- tween resolution -------------------------------------------------------------------------------
// act = { dur, beats:[sec...], actors:[{id,type,...props}], tweens:[{a,p,to,at,d,e}] }
// `at`: number (seconds) | "b3" | "b3+1.5" | "b3-0.5" | "end-2"
function resolveAt(at, act) {
  if (typeof at === 'number') return at;
  const m = /^(b(\d+)|end)\s*([+-]\s*[\d.]+)?$/.exec(String(at).trim());
  if (!m) return 0;
  const base = m[1] === 'end' ? act.dur : (act.beats[+m[2]] ?? act.beats[act.beats.length - 1] ?? 0);
  return base + (m[3] ? parseFloat(m[3].replace(/\s/g, '')) : 0);
}
function compile(act) {
  if (act._c) return act._c;
  const tracks = {}; // "actor|prop" -> sorted tweens with resolved `from`
  const ids = {}; act.actors.forEach((a) => { ids[a.id] = a; });
  ids.cam = ids.cam || { id: 'cam', type: 'cam', cx: W / 2, cy: H / 2, zoom: 1, rot: 0 };
  for (const tw of act.tweens || []) {
    const t0 = resolveAt(tw.at, act);
    const k = tw.a + '|' + tw.p;
    (tracks[k] = tracks[k] || []).push({ t0, d: Math.max(0.0001, tw.d ?? 0.01), to: tw.to, e: EASE[tw.e || 'inOut'] || EASE.inOut });
  }
  for (const k in tracks) {
    tracks[k].sort((x, y) => x.t0 - y.t0);
    const [aid, prop] = k.split('|'); let prev = ids[aid] ? ids[aid][prop] : undefined;
    if (prev === undefined) prev = 0;
    for (const tw of tracks[k]) { tw.from = prev; prev = tw.to; }
  }
  const order = act.actors.map((a, i) => ({ a, i })).sort((x, y) => ((x.a.z || 0) - (y.a.z || 0)) || (x.i - y.i)).map((x) => x.a);
  const byActor = {};
  for (const k in tracks) { const aid = k.split('|')[0]; (byActor[aid] = byActor[aid] || []).push(k); }
  return (act._c = { tracks, ids, order, byActor });
}
function evalProps(act, C, a, t) {
  const P = Object.assign({}, a);
  const ks = C.byActor[a.id];
  if (ks) for (const k of ks) {
    const prop = k.split('|')[1]; const list = C.tracks[k]; let v = a[prop] === undefined ? 0 : a[prop];
    for (const tw of list) {
      if (t < tw.t0) break;
      const p = clamp((t - tw.t0) / tw.d);
      const numArr = (x) => Array.isArray(x) && x.every((y) => typeof y === 'number');
      if (typeof tw.to === 'number' && typeof tw.from === 'number') v = lerp(tw.from, tw.to, tw.e(p));
      else if (prop !== 'hl' && numArr(tw.to) && numArr(tw.from) && tw.to.length === tw.from.length) v = tw.to.map((y, i) => lerp(tw.from[i], y, tw.e(p)));
      else v = p >= 1 ? tw.to : (p > 0 ? tw.from : v); // anything else (index lists, text) switches at the end of the tween
    }
    P[prop] = v;
  }
  return P;
}

// ---- dither grain: a fixed 512 px tile of 0..2 levels, shifted every frame; additive, so black stays black on average
let _grainTile = null;
function applyGrain(c, t) {
  if (!_grainTile) {
    const n = 512, cv = document.createElement('canvas'); cv.width = cv.height = n; const g = cv.getContext('2d'), im = g.createImageData(n, n), R = prng(1234567);
    for (let i = 0; i < n * n; i++) { const v = Math.floor(R() * 3); im.data[i * 4] = v; im.data[i * 4 + 1] = v; im.data[i * 4 + 2] = v; im.data[i * 4 + 3] = 255; }
    g.putImageData(im, 0, 0); _grainTile = cv;
  }
  const k = Math.floor(t * 24), ox = (k * 137) % 512, oy = (k * 89) % 512;
  c.save(); c.setTransform(1, 0, 0, 1, 0, 0); c.globalAlpha = 1; c.globalCompositeOperation = 'lighter';
  for (let y = -oy; y < H; y += 512) for (let x = -ox; x < W; x += 512) c.drawImage(_grainTile, x, y);
  c.restore();
}
// ---- act renderer -----------------------------------------------------------------------------------
const ACTORS = {};
const COLOR_PROPS = ['hue', 'color', 'bcol', 'rcol', 'tint', 'frame', 'glowc'];
const IMAGES = {};
window.__lang = 'de';
function renderAct(c, act, t) {
  const C = compile(act);
  c.setTransform(1, 0, 0, 1, 0, 0);
  c.globalAlpha = 1; c.globalCompositeOperation = 'source-over';
  c.fillStyle = PAL.bg0; c.fillRect(0, 0, W, H);
  const cam = evalProps(act, C, C.ids.cam, t);
  for (const a of C.order) {
    if (a.id === 'cam') continue;
    const P = evalProps(act, C, a, t);
    const fn = ACTORS[a.type]; if (!fn) continue;
    const o = P.o === undefined ? 1 : P.o; if (o <= 0.001) continue;
    const par = P.par === undefined ? 1 : P.par; // parallax: 0 = fixed to the screen, 1 = moves with the world
    c.save();
    c.translate(W / 2, H / 2);
    const z = 1 + (cam.zoom - 1) * par;
    c.scale(z, z);
    c.rotate((cam.rot || 0) * par * Math.PI / 180);
    c.translate(-(W / 2 + (cam.cx - W / 2) * par), -(H / 2 + (cam.cy - H / 2) * par));
    c.globalAlpha = o;
    for (const k of COLOR_PROPS) { if (typeof P[k] === 'number') P[k] = hueHex(P[k]); } // a bare number is a hue in degrees
    if (Array.isArray(P.cols)) P.cols = P.cols.map((x) => (typeof x === 'number' ? hueHex(x) : x));
    P.t = t; P.lang = window.__lang; P.act = act;
    if (P.noPos !== true) { c.translate(P.x || 0, P.y || 0); if (P.r) c.rotate(P.r * Math.PI / 180); const s = P.s === undefined ? 1 : P.s; c.scale(s * (P.flip ? -1 : 1), s); }
    fn(c, P, t);
    c.restore();
  }
  if (window.__grain) applyGrain(c, t); // off by default: random grain is incompressible in PNG, the encoder step adds the dither instead
  // act fade (dip to dark), in and out
  c.setTransform(1, 0, 0, 1, 0, 0); c.globalAlpha = 1;
  const f = Math.min(clamp(t / 0.6), clamp((act.dur - t) / 0.6));
  if (f < 1) { c.fillStyle = `rgba(5,7,14,${1 - f})`; c.fillRect(0, 0, W, H); }
}
window.addEventListener('DOMContentLoaded', () => {});
