// Concept actors B: terrain (loss landscape), compass, pixelpic, tower (layers of resolution), tree, fan, curve, flow, cycle, caption, symbol, art.

const _terrain = {};
function terrainModel(seed) {
  if (_terrain[seed]) return _terrain[seed];
  const R = prng(seed * 31 + 7), G = [];
  for (let i = 0; i < 5; i++) G.push({ x: (R() - 0.5) * 1.6, z: (R() - 0.5) * 1.6, a: 0.45 + R() * 0.55, s: 0.28 + R() * 0.22 });
  G.push({ x: 0.55, z: -0.35, a: -1.05, s: 0.42 }); // the deep valley: where the descent ends
  const h = (x, z) => { let v = 0.18; for (const g of G) v += g.a * Math.exp(-((x - g.x) ** 2 + (z - g.z) ** 2) / (g.s * g.s)); return v; };
  const path = []; let x = -0.7, z = 0.55;
  for (let i = 0; i < 240; i++) { path.push([x, z]); const e = 0.01, gx = (h(x + e, z) - h(x - e, z)) / (2 * e), gz = (h(x, z + e) - h(x, z - e)) / (2 * e); x -= gx * 0.018; z -= gz * 0.018; x = clamp(x, -1, 1); z = clamp(z, -1, 1); }
  return (_terrain[seed] = { h, path });
}
let _tl = null, _frontY = 0;
ACTORS.terrain = (c0, P, t) => {
  if (!_tl) { _tl = document.createElement('canvas'); _tl.width = W; _tl.height = H; }
  const c = _tl.getContext('2d'); c.setTransform(1, 0, 0, 1, 0, 0); c.clearRect(0, 0, W, H); c.translate(W / 2, H / 2 - 120);
  terrainDraw(c, P, t);
  c.setTransform(1, 0, 0, 1, 0, 0); c.globalCompositeOperation = 'destination-out';
  const y0 = H / 2 - 120 + _frontY - 10, fg = c.createLinearGradient(0, y0, 0, y0 + 120); fg.addColorStop(0, 'rgba(0,0,0,0)'); fg.addColorStop(1, 'rgba(0,0,0,1)'); c.fillStyle = fg; c.fillRect(0, y0, W, H); c.globalCompositeOperation = 'source-over';
  c0.drawImage(_tl, -W / 2, -H / 2 + 120);
};
function terrainDraw(c, P, t) {
  const M = terrainModel(P.seed || 2), G = 34, S = 620, Hs = 230, p = clamp(P.p || 0), fog = P.fog === undefined ? 0 : P.fog, ang = (P.rot === undefined ? 0.3 : P.rot) + Math.sin(t * 0.2) * 0.02;
  const proj = (x, z, h) => { const rx = x * Math.cos(ang) - z * Math.sin(ang), rz = x * Math.sin(ang) + z * Math.cos(ang), f = 0.62 + 0.38 * ((rz + 1.2) / 2.4); return [rx * S * f, rz * 150 - h * Hs * f + 40]; };
  for (let iz = 0; iz <= G; iz++) {
    const z = -1 + 2 * iz / G, pts = [];
    for (let ix = 0; ix <= G; ix++) { const x = -1 + 2 * ix / G; pts.push([...proj(x, z, M.h(x, z)), M.h(x, z)]); }
    c.beginPath(); c.moveTo(pts[0][0], pts[0][1]); pts.forEach((q) => c.lineTo(q[0], q[1]));
    for (let ix = G; ix >= 0; ix--) c.lineTo(pts[ix][0], pts[ix][1] + 150); c.closePath(); c.fillStyle = '#070c18'; c.fill();
    if (iz === G) _frontY = pts.reduce((m, q) => Math.max(m, q[1]), -1e9);
    const depth = iz / G;
    const grd = c.createLinearGradient(pts[0][0], 0, pts[G][0], 0);
    for (let k = 0; k <= 8; k++) { const q = pts[Math.round(k / 8 * G)]; grd.addColorStop(k / 8, rgba(mix('#2ec4b6', '#e8a83a', clamp((q[2] - 0.1) / 1.0)), (0.25 + 0.75 * depth) * (1 - fog * (1 - depth)))); }
    c.strokeStyle = grd; c.lineWidth = 1.5 + depth * 0.8; c.beginPath(); pts.forEach((q, i) => (i ? c.lineTo(q[0], q[1]) : c.moveTo(q[0], q[1]))); c.stroke();
  }
  // the optimiser rolls down: glowing ball with a fading trail
  const n = M.path.length, idx = p * (n - 1), i0 = Math.floor(idx), f = idx - i0;
  const pos = (i) => { const q = M.path[Math.min(n - 1, i)]; const hh = M.h(q[0], q[1]); const s = proj(q[0], q[1], hh); return s; };
  if (p > 0) {
    c.save(); c.globalCompositeOperation = 'lighter'; c.lineCap = 'round';
    for (let i = Math.max(0, i0 - 70); i < i0; i++) { const a = pos(i), b = pos(i + 1), u = (i - (i0 - 70)) / 70; c.strokeStyle = rgba('#8be0ff', 0.7 * u); c.lineWidth = 2 + 5 * u; c.beginPath(); c.moveTo(a[0], a[1]); c.lineTo(b[0], b[1]); c.stroke(); }
    c.restore();
    const a = pos(i0), b = pos(i0 + 1), bx = lerp(a[0], b[0], f), by = lerp(a[1], b[1], f) - 8;
    glowAdd(c, bx, by, 60, '#8be0ff', 0.7); const bg = c.createRadialGradient(bx - 3, by - 3, 1, bx, by, 11); bg.addColorStop(0, '#ffffff'); bg.addColorStop(1, '#7fd8ff'); c.fillStyle = bg; c.beginPath(); c.arc(bx, by, 11, 0, TAU); c.fill();
  }
  if (P.hiker) { const q = M.path[Math.min(n - 1, Math.floor(idx))], s = proj(q[0], q[1], M.h(q[0], q[1])); c.save(); c.translate(s[0], s[1]); c.scale(0.2, 0.2); ACTORS.figure(c, { pose: 'walk', color: '#d8d4c8' }, t); c.restore(); }
}

ACTORS.compass = (c, P, t) => {
  const R = 150, ang = (P.ang || 0) * Math.PI / 180, wob = P.wobble || 0, a = ang + wob * Math.sin(t * 9) * 0.6;
  glowAdd(c, 0, 0, R * 2.2, '#ffbf5a', 0.12 * (P.glow === undefined ? 1 : P.glow));
  const g = c.createLinearGradient(-R, -R, R, R); g.addColorStop(0, '#46567c'); g.addColorStop(1, '#16213a'); c.strokeStyle = g; c.lineWidth = 14; c.beginPath(); c.arc(0, 0, R, 0, TAU); c.stroke();
  c.strokeStyle = 'rgba(200,215,240,0.35)'; c.lineWidth = 2; c.beginPath(); c.arc(0, 0, R - 18, 0, TAU); c.stroke();
  c.fillStyle = 'rgba(8,14,26,0.85)'; c.beginPath(); c.arc(0, 0, R - 20, 0, TAU); c.fill();
  for (let i = 0; i < 32; i++) { const aa = i / 32 * TAU, l = i % 8 === 0 ? 26 : i % 4 === 0 ? 17 : 9; c.strokeStyle = i % 8 === 0 ? 'rgba(232,168,58,0.9)' : 'rgba(180,195,225,0.5)'; c.lineWidth = i % 8 === 0 ? 3 : 1.5; c.beginPath(); c.moveTo(Math.cos(aa) * (R - 22), Math.sin(aa) * (R - 22)); c.lineTo(Math.cos(aa) * (R - 22 - l), Math.sin(aa) * (R - 22 - l)); c.stroke(); }
  c.save(); c.rotate(a);
  c.fillStyle = '#e8a83a'; c.beginPath(); c.moveTo(0, -R + 36); c.lineTo(15, 0); c.lineTo(-15, 0); c.closePath(); c.fill();
  c.fillStyle = '#2ec4b6'; c.beginPath(); c.moveTo(0, R - 36); c.lineTo(15, 0); c.lineTo(-15, 0); c.closePath(); c.fill();
  c.restore(); c.fillStyle = '#ece9e2'; c.beginPath(); c.arc(0, 0, 9, 0, TAU); c.fill(); c.fillStyle = '#16213a'; c.beginPath(); c.arc(0, 0, 4, 0, TAU); c.fill();
};

// ---- pixelpic: a picture that gains resolution --------------------------------------------------------
const RES = [2, 3, 4, 6, 8, 12, 16, 24, 32, 48, 64, 96];
function picCoast(u, v) {
  const hy = 0.64; let r, g, b;
  if (v < hy) { const k = v / hy; r = lerp(20, 246, k * k); g = lerp(34, 150, k * k); b = lerp(96, 100, k * k) + (1 - k) * 40; const dx = u - 0.2, dy = v - 0.2; if (dx * dx + dy * dy < 0.0022) { r = 252; g = 244; b = 224; } if (fract(Math.sin(u * 913.3 + v * 271.7) * 43758.5453) > 0.985 && k < 0.6) { r = g = b = 240; } }
  else { const k = (v - hy) / (1 - hy); r = lerp(40, 10, k); g = lerp(96, 30, k); b = lerp(130, 62, k); if (Math.sin(u * 70 + v * 45) > 0.9) { r += 60; g += 70; b += 70; } }
  const cx = 0.62, top = 0.3, wd = lerp(0.03, 0.052, clamp((v - top) / (hy - top)));
  if (v > top && v < hy && Math.abs(u - cx) < wd) { const st = Math.floor((v - top) / 0.07) % 2; [r, g, b] = st ? [240, 232, 208] : [44, 70, 140]; }
  if (v > 0.25 && v <= top && Math.abs(u - cx) < 0.027) { [r, g, b] = [255, 226, 130]; }
  if (v > 0.2 && v <= 0.25 && Math.abs(u - cx) < 0.045 * (v - 0.2) / 0.05) { [r, g, b] = [200, 70, 70]; }
  if (u > cx && v > 0.255 && v < 0.295 + (u - cx) * 0.16 && v > 0.28 - (u - cx) * 0.1) { const a = clamp(1 - (u - cx) * 1.5) * 0.55; r = lerp(r, 255, a); g = lerp(g, 230, a); b = lerp(b, 150, a); }
  return [r, g, b];
}
function drawPix(c, P, t, w, h) {
  const lv = clamp(P.lvl === undefined ? 11 : P.lvl, 0, RES.length - 1), l0 = Math.floor(lv), f = lv - l0, noise = P.noise || 0;
  const level = (idx, alpha) => {
    const N = RES[idx], cw = w / N, ch = h / N; c.globalAlpha *= alpha;
    for (let j = 0; j < N; j++) for (let i = 0; i < N; i++) {
      let [r, g, b] = picCoast((i + 0.5) / N, (j + 0.5) / N);
      if (noise > 0) { const hs = fract(Math.sin((i * 12.9898 + j * 78.233 + Math.floor(t * 7) * 3.1) * 43758.5453)); if (hs < noise) { const e = (fract(hs * 97.1) - 0.5) * 180 * noise; r += e; g -= e * 0.6; b += e * 0.9; } }
      c.fillStyle = `rgb(${r | 0},${g | 0},${b | 0})`; c.fillRect(-w / 2 + i * cw, -h / 2 + j * ch, cw + 0.6, ch + 0.6);
    }
    c.globalAlpha /= alpha;
  };
  level(l0, 1); if (f > 0.001 && l0 + 1 < RES.length) level(l0 + 1, f);
}
ACTORS.pixelpic = (c, P, t) => {
  const w = P.w || 480, h = P.h || 320; glowAdd(c, 0, 0, w * 0.9, P.glowc || '#5fb8e8', 0.1 * (P.glow === undefined ? 1 : P.glow));
  drawPix(c, P, t, w, h);
  c.strokeStyle = rgba(P.frame || '#8fa4cf', 0.7); c.lineWidth = 3; c.strokeRect(-w / 2, -h / 2, w, h);
  if (P.scan) { const y = (fract(t * 0.6) - 0.5) * h; const g = c.createLinearGradient(0, y - 30, 0, y + 6); g.addColorStop(0, 'rgba(120,255,220,0)'); g.addColorStop(1, 'rgba(120,255,220,0.55)'); c.fillStyle = g; c.fillRect(-w / 2, y - 30, w, 36); }
};
ACTORS.tower = (c, P, t) => { // glass plates of rising resolution under a single falling seed of light
  const lit = P.lit === undefined ? 5 : P.lit, n = 5, gap = P.gap || 128;
  glowAdd(c, 0, -60, 220, '#bfe9ff', 0.28);
  c.save(); c.globalCompositeOperation = 'lighter'; const lg = c.createLinearGradient(0, -60, 0, (n - 1) * gap + 80); lg.addColorStop(0, 'rgba(191,233,255,0.5)'); lg.addColorStop(1, 'rgba(191,233,255,0.03)');
  c.fillStyle = lg; c.beginPath(); c.moveTo(-16, -60); c.lineTo(16, -60); c.lineTo(190 + (n - 1) * 24, (n - 1) * gap + 80); c.lineTo(-190 - (n - 1) * 24, (n - 1) * gap + 80); c.closePath(); c.globalAlpha *= clamp(lit) * 0.6; c.fill(); c.restore();
  for (let i = 0; i < n; i++) {
    const a = clamp(lit - i); if (a <= 0) continue; const w = 220 + i * 48, h = 150 + i * 30, y = i * gap;
    c.save(); c.globalAlpha *= a; c.translate(0, y); c.transform(1, 0, -0.34, 0.42, 0, 0);
    c.save(); drawPix(c, { lvl: 1 + i * 2.3 }, t, w, h); c.restore();
    c.strokeStyle = 'rgba(191,233,255,0.85)'; c.lineWidth = 3; c.strokeRect(-w / 2, -h / 2, w, h); c.fillStyle = 'rgba(191,233,255,0.06)'; c.fillRect(-w / 2, -h / 2, w, h); c.restore();
  }
};

ACTORS.tree = (c, P, t) => {
  const g = clamp(P.grow === undefined ? 1 : P.grow), R = prng(P.seed || 6), col = P.color || '#56c596';
  const branch = (x, y, a, len, d) => {
    const f = clamp(g * 9 - d); if (f <= 0 || d > 8) return;
    const sw = Math.sin(t * 0.8 + d * 0.9) * 0.035, ea = a + sw, ex = x + Math.cos(ea) * len * f, ey = y + Math.sin(ea) * len * f;
    c.strokeStyle = mix('#5b4636', '#8b6f55', d / 8); c.lineWidth = Math.max(1.5, (9 - d) * 2.6); c.lineCap = 'round'; c.beginPath(); c.moveTo(x, y); c.lineTo(ex, ey); c.stroke();
    if (f >= 1) { if (d >= 7) { const lf = clamp((g - 0.78) * 5); if (lf > 0) { glowAdd(c, ex, ey, 22 * lf, col, 0.55); c.fillStyle = rgba(mix(col, '#c8ffe0', R()), 0.9 * lf); c.beginPath(); c.ellipse(ex, ey, 7 * lf, 4 * lf, ea, 0, TAU); c.fill(); } }
      else { const sp = 0.42 + R() * 0.16; branch(ex, ey, ea - sp, len * 0.76, d + 1); branch(ex, ey, ea + sp, len * 0.76, d + 1); if (d % 3 === 1) branch(ex, ey, ea + (R() - 0.5) * 0.3, len * 0.6, d + 1); } }
  };
  branch(0, 0, -Math.PI / 2, 150, 0);
};

ACTORS.fan = (c, P, t) => { // a folded screen that unfolds into a flat plan
  const f = clamp(P.fold === undefined ? 1 : P.fold), n = P.n || 7, pw = 90, ph = 330, al = (1 - EASE.inOut(f)) * 1.25, cw = pw * Math.cos(al), dz = pw * Math.sin(al) * 0.5, total = cw * n;
  c.translate(-total / 2, 0);
  for (let i = 0; i < n; i++) {
    const x0 = i * cw, x1 = (i + 1) * cw, d0 = (i % 2 ? 1 : -1) * dz, d1 = -d0, sh = i % 2 ? 0.55 : 1;
    c.beginPath(); c.moveTo(x0, -ph / 2 + d0); c.lineTo(x1, -ph / 2 + d1); c.lineTo(x1, ph / 2 + d1); c.lineTo(x0, ph / 2 + d0); c.closePath();
    const g = c.createLinearGradient(x0, 0, x1, 0); g.addColorStop(0, mix('#14203a', '#35507e', sh)); g.addColorStop(1, mix('#14203a', '#2a4268', sh)); c.fillStyle = g; c.fill();
    c.strokeStyle = rgba('#8fb4e8', 0.7); c.lineWidth = 2; c.stroke();
    c.save(); c.clip(); c.strokeStyle = rgba('#5fb8e8', 0.35 * f); c.lineWidth = 1.5; for (let k = 1; k < 7; k++) { c.beginPath(); c.moveTo(x0, -ph / 2 + k * ph / 7); c.lineTo(x1, -ph / 2 + k * ph / 7); c.stroke(); } c.restore();
  }
  if (f > 0.6) { c.strokeStyle = rgba('#e8a83a', 0.9 * (f - 0.6) / 0.4); c.lineWidth = 3; strokePartial(c, [[total * 0.12, 100], [total * 0.12, -60], [total * 0.5, -120], [total * 0.88, -60], [total * 0.88, 100]], (f - 0.6) / 0.4); }
};

ACTORS.curve = (c, P, t) => { // a falling line of progress
  const w = P.w || 700, h = P.h || 340, p = clamp(P.p === undefined ? 1 : P.p), col = P.color || '#2ec4b6', N = 80, pts = [];
  for (let i = 0; i <= N; i++) { const u = i / N; pts.push([u * w, h * (0.06 + 0.88 * (1 - Math.exp(-3.2 * u))) + Math.sin(u * 22) * 7 * (1 - u)]); }
  c.strokeStyle = 'rgba(140,160,200,0.25)'; c.lineWidth = 2; c.beginPath(); c.moveTo(0, 0); c.lineTo(0, h + 14); c.lineTo(w + 14, h + 14); c.stroke();
  const m = Math.floor(N * p), vis = pts.slice(0, m + 1); if (vis.length < 2) return;
  c.beginPath(); c.moveTo(vis[0][0], h + 14); vis.forEach((q) => c.lineTo(q[0], q[1])); c.lineTo(vis[vis.length - 1][0], h + 14); c.closePath();
  const ag = c.createLinearGradient(0, 0, 0, h); ag.addColorStop(0, rgba(col, 0.28)); ag.addColorStop(1, rgba(col, 0)); c.fillStyle = ag; c.fill();
  c.save(); c.globalCompositeOperation = 'lighter'; c.strokeStyle = rgba(col, 0.95); c.lineWidth = 5; c.lineJoin = 'round'; c.beginPath(); vis.forEach((q, i) => (i ? c.lineTo(q[0], q[1]) : c.moveTo(q[0], q[1]))); c.stroke(); c.restore();
  const e = vis[vis.length - 1]; c.strokeStyle = rgba('#ece9e2', 0.9); c.lineWidth = 3; c.beginPath(); c.arc(e[0], e[1], 11, 0, TAU); c.stroke();
};

ACTORS.flow = (c, P, t) => { // a stream of small chevrons along a gentle curve
  const x0 = P.x0 || 0, y0 = P.y0 || 0, x1 = P.x1 === undefined ? 600 : P.x1, y1 = P.y1 === undefined ? 0 : P.y1, n = P.n || 12, col = P.color || '#5fb8e8', sp = P.speed === undefined ? 0.25 : P.speed, bend = P.bend === undefined ? -120 : P.bend, p = P.p === undefined ? 1 : P.p;
  for (let i = 0; i < n; i++) {
    const u = fract(t * sp + i / n), m = 1 - u, cx = (x0 + x1) / 2, cy = (y0 + y1) / 2 + bend, x = m * m * x0 + 2 * m * u * cx + u * u * x1, y = m * m * y0 + 2 * m * u * cy + u * u * y1;
    const dx = 2 * m * (cx - x0) + 2 * u * (x1 - cx), dy = 2 * m * (cy - y0) + 2 * u * (y1 - cy), a = Math.atan2(dy, dx), al = Math.sin(u * Math.PI) * p;
    c.save(); c.translate(x, y); c.rotate(a); c.strokeStyle = rgba(col, al * 0.9); c.lineWidth = 4; c.lineCap = 'round'; c.beginPath(); c.moveTo(-9, -11); c.lineTo(5, 0); c.lineTo(-9, 11); c.stroke(); glowAdd(c, 0, 0, 24, col, 0.2 * al); c.restore();
  }
};

ACTORS.cycle = (c, P, t) => { // a ring of flowing chevrons; `lit` segments glow
  const R = P.R || 230, n = P.n || 4, lit = P.lit === undefined ? n : P.lit, col = P.color || '#2ec4b6', sp = P.speed === undefined ? 0.12 : P.speed, cols = P.cols || [col];
  for (let i = 0; i < n; i++) {
    const a0 = -Math.PI / 2 + i / n * TAU + 0.08, a1 = -Math.PI / 2 + (i + 1) / n * TAU - 0.08, l = clamp(lit - i), cc = cols[i % cols.length];
    c.strokeStyle = rgba(cc, 0.18 + 0.7 * l); c.lineWidth = 8 + 6 * l; c.lineCap = 'round'; c.beginPath(); c.arc(0, 0, R, a0, a1); c.stroke();
    if (l > 0.01) glowAdd(c, Math.cos((a0 + a1) / 2) * R, Math.sin((a0 + a1) / 2) * R, 70, cc, 0.28 * l);
  }
  const m = 14; for (let k = 0; k < m; k++) { const a = -Math.PI / 2 + fract(t * sp + k / m) * TAU, seg = Math.floor(fract(t * sp + k / m) * n), l = clamp(lit - seg); if (l <= 0) continue;
    c.save(); c.translate(Math.cos(a) * R, Math.sin(a) * R); c.rotate(a + Math.PI / 2); c.strokeStyle = rgba('#ffffff', 0.85 * l); c.lineWidth = 3; c.beginPath(); c.moveTo(-8, 7); c.lineTo(0, -4); c.lineTo(8, 7); c.stroke(); c.restore(); }
};

ACTORS.caption = (c, P) => {
  const txt = (typeof P.text === 'object' ? P.text[P.lang] || P.text.de : P.text) || '', lines = txt.split('\n'), size = P.size || 64, p = P.p === undefined ? 1 : P.p;
  c.font = `${P.italic ? 'italic ' : ''}${P.bold ? '700 ' : '400 '}${size}px ${P.font === 'sans' ? '"Instrument Sans","Noto Sans","DejaVu Sans",sans-serif' : '"Newsreader","Noto Serif",Georgia,serif'}`;
  c.textAlign = P.align || 'center'; c.textBaseline = 'middle'; const total = txt.replace(/\n/g, '').length; let rem = Math.floor(clamp(p) * total + 0.001);
  const lh = size * (P.lh || 1.25), y0 = -((lines.length - 1) * lh) / 2;
  lines.forEach((ln, i) => { const s = ln.slice(0, Math.max(0, rem)); rem -= ln.length; if (!s) return; c.shadowColor = rgba(P.color || '#ece9e2', 0.35); c.shadowBlur = 18; c.fillStyle = P.color || '#ece9e2'; c.fillText(s, 0, y0 + i * lh); c.shadowBlur = 0; });
};

ACTORS.symbol = (c, P) => { // the CorvinOS mark (brand colours), stroke-drawn
  const p = clamp(P.p === undefined ? 1 : P.p), k = (P.size || 260) / 96;
  c.scale(k, k); c.translate(-60, -60); c.lineCap = 'round'; c.lineJoin = 'round'; c.strokeStyle = '#eef1f5'; c.lineWidth = 8;
  strokePartial(c, [[28, 40], [56, 60], [28, 80]], clamp(p * 2));
  if (p > 0.45) { c.fillStyle = '#eef1f5'; c.globalAlpha *= clamp((p - 0.45) * 4); c.beginPath(); c.roundRect(66, 72, 30, 9, 2); c.fill(); }
  if (p > 0.7) { c.globalAlpha = clamp((p - 0.7) * 4); c.fillStyle = '#c9a227'; c.strokeStyle = '#eef1f5'; c.lineWidth = 2; c.beginPath(); c.arc(80, 50, 10, 0, TAU); c.fill(); c.stroke(); }
};

ACTORS.art = (c, P) => { // an external illustration (for instance a Penpot design), drawn centred
  const im = IMAGES[P.src]; if (!im) return;
  const w = P.w || im.width, h = P.h || im.height, p = clamp(P.p === undefined ? 1 : P.p);
  if (p <= 0) return;
  const rad = P.radius || 0;
  if (P.glow) { glowAdd(c, 0, 0, Math.max(w, h) * 0.7, P.glowc || PAL.amber, P.glow); }
  c.save();
  c.beginPath(); if (rad) c.roundRect(-w / 2, -h / 2, w * p, h, rad); else c.rect(-w / 2, -h / 2, w * p, h); c.clip(); // left-to-right wipe while p < 1
  c.drawImage(im, -w / 2, -h / 2, w, h);
  c.restore();
};
