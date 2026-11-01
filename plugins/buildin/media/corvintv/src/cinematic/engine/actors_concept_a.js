// Concept actors A: constellation, pages, arch, gate, token, bubble, pedestal, crystal, gear, blueprint, coin, lamps.

ACTORS.constellation = (c, P, t) => {
  const N = P.nodes || [], Lk = P.links || [], p = P.p === undefined ? N.length : P.p, lp = P.lp === undefined ? 1 : P.lp;
  const hl = new Set(P.hl || []), dim = P.dim || 0, base = P.size || 7, col = P.color || '#bfe9ff';
  c.save(); c.globalCompositeOperation = 'lighter';
  Lk.forEach(([i, j], k) => {
    const a = N[i], b = N[j]; if (!a || !b) return;
    const vis = Math.min(clamp(p - i), clamp(p - j)); if (vis <= 0) return;
    const f = clamp(lp * Lk.length - k) * vis; if (f <= 0) return;
    const bx = a[0] + (b[0] - a[0]) * f, by = a[1] + (b[1] - a[1]) * f, isH = hl.has(i) && hl.has(j), al = isH ? 0.95 : 0.42 * (1 - dim * 0.7);
    const gr = c.createLinearGradient(a[0], a[1], bx, by); gr.addColorStop(0, rgba(a[2] || col, al)); gr.addColorStop(1, rgba(b[2] || col, al));
    c.strokeStyle = gr; c.lineWidth = isH ? 2.6 : 1.3; c.beginPath(); c.moveTo(a[0], a[1]); c.lineTo(bx, by); c.stroke();
  });
  c.restore();
  N.forEach((n, i) => {
    const a = clamp(p - i); if (a <= 0) return;
    const isH = hl.has(i), col2 = n[2] || col, sz = (n[3] || 1) * base * EASE.back(a) * (isH ? 1.4 : 1), al = a * (1 - (hl.size && !isH ? dim * 0.65 : 0)), tw = 0.78 + 0.22 * Math.sin(t * 1.6 + i * 1.9);
    glowAdd(c, n[0], n[1], sz * 6.5 * (isH ? 1.6 : 1), col2, 0.5 * al * tw);
    c.fillStyle = rgba('#ffffff', 0.95 * al); c.beginPath(); c.arc(n[0], n[1], sz * 0.5, 0, TAU); c.fill();
    c.strokeStyle = rgba(col2, 0.6 * al * tw); c.lineWidth = 1.3; const L = sz * (isH ? 5.5 : 3.2);
    c.beginPath(); c.moveTo(n[0] - L, n[1]); c.lineTo(n[0] + L, n[1]); c.moveTo(n[0], n[1] - L); c.lineTo(n[0], n[1] + L); c.stroke();
  });
};

ACTORS.pages = (c, P, t) => {
  const m = P.m || 0, n = P.n || 5, tg = (P.targets || []).map(([x, y]) => [(x - (P.x || 0)) / (P.s || 1), (y - (P.y || 0)) / (P.s || 1)]), R = prng(21);
  for (let k = 0; k < n; k++) {
    const rot = (k - (n - 1) / 2) * 0.07, ox = (k - (n - 1) / 2) * 16, oy = (k - (n - 1) / 2) * -6, a = 1 - clamp(m * 1.6 - k * 0.1);
    if (a > 0.01) {
      c.save(); c.translate(ox, oy - m * 30 * (k + 1) * 0.3); c.rotate(rot + m * (k - 2) * 0.12); c.globalAlpha *= a;
      const g = c.createLinearGradient(-110, -150, 110, 150); g.addColorStop(0, '#efe8d6'); g.addColorStop(1, '#cfc7b2');
      c.fillStyle = g; c.beginPath(); c.roundRect(-110, -150, 220, 300, 6); c.fill();
      c.fillStyle = 'rgba(60,55,45,0.55)';
      for (let r = 0; r < 12; r++) { const w = 130 + ((r * 37 + k * 11) % 50); c.fillRect(-86, -118 + r * 21, w, 6); }
      c.restore();
    }
    const cnt = 48;
    for (let i = 0; i < cnt; i++) {
      const sx = ox + (R() - 0.5) * 200, sy = oy + (R() - 0.5) * 280, d = R() * 0.45, tgt = tg.length ? tg[(k * 7 + i * 3) % tg.length] : [sx, sy - 400];
      const u = EASE.inOut(clamp((m - 0.15) * 1.5 - d)); if (u <= 0 || u >= 1) { if (u >= 1) continue; else continue; }
      const px = lerp(sx, tgt[0], u) + Math.sin(u * Math.PI) * (R() - 0.5) * 220, py = lerp(sy, tgt[1], u) - Math.sin(u * Math.PI) * 120;
      glowAdd(c, px, py, 14, '#ffe3a0', 0.55 * Math.sin(u * Math.PI));
    }
  }
};

ACTORS.arch = (c, P, t) => {
  const lit = P.lit || 0, key = P.key === undefined ? 1 : P.key, R = P.R || 330, th = P.th || 96, n = 7, ri = R - th / 2, ro = R + th / 2;
  // feet
  c.fillStyle = '#121a2e'; c.fillRect(-ro - 6, 0, th + 12, 26); c.fillRect(ri - 6, 0, th + 12, 26);
  c.fillStyle = 'rgba(0,0,0,0.35)'; c.fillRect(-ro - 40, 26, 2 * ro + 80, 8);
  for (let i = 0; i < n; i++) {
    const a0 = Math.PI - i * Math.PI / n - 0.011, a1 = Math.PI - (i + 1) * Math.PI / n + 0.011, isKey = i === 3;
    if (isKey && key <= 0) continue;
    const ke = isKey ? EASE.drop(clamp(key)) : 1, dy = isKey ? -(1 - ke) * 1000 : 0, l = clamp(lit - i);
    c.save(); c.translate(0, dy);
    c.beginPath(); c.arc(0, 0, ro, -a0, -a1, false); c.arc(0, 0, ri, -a1, -a0, true); c.closePath();
    const am = (a0 + a1) / 2, gx = Math.cos(am) * R, gy = -Math.sin(am) * R, gr = c.createRadialGradient(gx, gy, 4, gx, gy, th * 1.1);
    gr.addColorStop(0, mix('#33466e', '#f7cf7e', l)); gr.addColorStop(1, mix('#17213a', '#c4861a', l));
    c.fillStyle = gr; c.fill(); c.strokeStyle = rgba(mix('#4a5d88', '#ffe3a8', l), 0.7); c.lineWidth = 2; c.stroke();
    if (l > 0.01) glowAdd(c, gx, gy, 150, '#ffbf5a', 0.32 * l);
    c.restore();
  }
  if (key > 0.7 && key < 1.3) { const u = clamp((key - 0.72) / 0.5); for (let k = 0; k < 2; k++) { c.strokeStyle = rgba('#ffe3a8', (1 - u) * 0.6); c.lineWidth = 3; c.beginPath(); c.ellipse(0, -R, 40 + u * (200 + k * 120), 20 + u * (60 + k * 30), 0, 0, TAU); c.stroke(); } }
};

ACTORS.gate = (c, P, t) => {
  const open = P.open || 0, kind = P.kind || 'seal', col = P.color || '#2ec4b6', gl = P.glow === undefined ? open : P.glow, w = 120, hgt = 250;
  const arch = (hw, top, bot) => { c.beginPath(); c.moveTo(-hw, bot); c.lineTo(-hw, top); c.arc(0, top, hw, Math.PI, 0); c.lineTo(hw, bot); c.closePath(); };
  // light spilling out of the opened gate
  if (gl > 0.01) { glowAdd(c, 0, -150, 380, col, 0.26 * gl); c.save(); c.globalCompositeOperation = 'lighter'; const lg = c.createLinearGradient(0, -hgt, 0, 140); lg.addColorStop(0, rgba(col, 0)); lg.addColorStop(1, rgba(col, 0.4 * gl)); c.fillStyle = lg; c.beginPath(); c.moveTo(-w + 20, 0); c.lineTo(w - 20, 0); c.lineTo(w + 110, 140); c.lineTo(-w - 110, 140); c.closePath(); c.fill(); c.restore(); }
  // portal
  c.save(); arch(w - 18, -hgt + 20, 0); c.clip();
  const pg = c.createLinearGradient(0, -hgt, 0, 0); pg.addColorStop(0, mix('#0a1020', col, 0.8 * gl)); pg.addColorStop(1, mix('#0a1020', '#ffffff', 0.85 * gl)); c.fillStyle = pg; c.fillRect(-w, -hgt - 40, 2 * w, hgt + 60);
  if (gl > 0.05) { c.globalCompositeOperation = 'lighter'; for (let i = 0; i < 9; i++) { const a = -Math.PI / 2 + (i - 4) * 0.22 + Math.sin(t * 0.5 + i) * 0.03; c.strokeStyle = rgba('#ffffff', 0.07 * gl); c.lineWidth = 14; c.beginPath(); c.moveTo(0, -20); c.lineTo(Math.cos(a) * 420, -20 + Math.sin(a) * 420); c.stroke(); } c.globalCompositeOperation = 'source-over'; }
  // door leaves
  const sh = EASE.inOut(clamp(open)) * (w - 20);
  const dg = c.createLinearGradient(-w, 0, w, 0); dg.addColorStop(0, '#16213a'); dg.addColorStop(1, '#223152'); c.fillStyle = dg;
  c.fillRect(-w - sh, -hgt - 40, w, hgt + 60); c.fillRect(sh, -hgt - 40, w, hgt + 60);
  c.strokeStyle = 'rgba(120,140,180,0.25)'; c.lineWidth = 2; for (let i = 1; i < 5; i++) { c.beginPath(); c.moveTo(-w - sh + i * 24, -hgt); c.lineTo(-w - sh + i * 24, 0); c.moveTo(sh + i * 24, -hgt); c.lineTo(sh + i * 24, 0); c.stroke(); }
  c.restore();
  // frame
  c.save(); const fg = c.createLinearGradient(-w, -hgt, w, 0); fg.addColorStop(0, '#3d4f78'); fg.addColorStop(1, '#1b2640'); c.fillStyle = fg; c.beginPath(); c.moveTo(-w - 22, 6); c.lineTo(-w - 22, -hgt + 20); c.arc(0, -hgt + 20, w + 22, Math.PI, 0); c.lineTo(w + 22, 6); c.closePath(); c.moveTo(-(w - 18), 0); c.lineTo(-(w - 18), -hgt + 20); c.arc(0, -hgt + 20, w - 18, Math.PI, 0); c.lineTo(w - 18, 0); c.closePath(); c.fill('evenodd'); c.restore();
  c.strokeStyle = rgba(mix('#4d618e', col, gl * 0.8), 0.9); c.lineWidth = 3; arch(w + 22, -hgt + 20, 6); c.stroke(); arch(w - 18, -hgt + 20, 0); c.stroke();
  // emblem on the keystone
  const ex = 0, ey = -hgt - w * 0.9 + 6; c.save(); c.translate(ex, ey); c.strokeStyle = rgba(mix('#8fa4cf', col, gl), 0.95); c.fillStyle = c.strokeStyle; c.lineWidth = 3.5;
  if (kind === 'keyhole') { c.beginPath(); c.arc(0, -6, 12, 0, TAU); c.fill(); c.beginPath(); c.moveTo(-6, 4); c.lineTo(6, 4); c.lineTo(9, 28); c.lineTo(-9, 28); c.closePath(); c.fill(); }
  else if (kind === 'compass') { c.beginPath(); c.arc(0, 8, 24, 0, TAU); c.stroke(); for (let i = 0; i < 4; i++) { c.save(); c.translate(0, 8); c.rotate(i * Math.PI / 2 + t * 0.3 * gl); c.beginPath(); c.moveTo(0, -24); c.lineTo(5, -8); c.lineTo(-5, -8); c.closePath(); c.fill(); c.restore(); } }
  else { c.beginPath(); c.arc(0, 8, 24, 0, TAU); c.stroke(); c.beginPath(); for (let i = 0; i < 5; i++) { const a = -Math.PI / 2 + i * TAU / 5 * 2; c.lineTo(Math.cos(a) * 15, 8 + Math.sin(a) * 15); } c.closePath(); c.stroke(); }
  c.restore();
  c.fillStyle = '#0d1424'; c.fillRect(-w - 40, 0, 2 * w + 80, 14);
};

ACTORS.token = (c, P, t) => {
  const shape = P.shape || 'seed', hue = P.hue || '#8bd0ff', bob = Math.sin(t * 1.4 + (P.seed || 0) * 2) * 4, g = P.glow === undefined ? 0.6 : P.glow;
  c.translate(0, bob); glowAdd(c, 0, 0, 70, hue, 0.28 * g); c.fillStyle = hue; c.strokeStyle = rgba('#ffffff', 0.7); c.lineWidth = 2;
  const fill = (a, b) => { const gr = c.createLinearGradient(0, -34, 0, 34); gr.addColorStop(0, a); gr.addColorStop(1, b); c.fillStyle = gr; c.fill(); c.stroke(); };
  if (shape === 'seed') { c.beginPath(); c.moveTo(0, -34); c.quadraticCurveTo(30, -2, 0, 34); c.quadraticCurveTo(-30, -2, 0, -34); fill(mix(hue, '#ffffff', 0.5), hue); c.strokeStyle = rgba('#fff', 0.5); c.beginPath(); c.moveTo(0, -20); c.lineTo(0, 22); c.stroke(); }
  else if (shape === 'leaf') { c.beginPath(); c.moveTo(-30, 26); c.quadraticCurveTo(-34, -30, 30, -30); c.quadraticCurveTo(34, 30, -30, 26); fill(mix(hue, '#ffffff', 0.4), mix(hue, '#000000', 0.2)); }
  else if (shape === 'diamond') { c.beginPath(); c.moveTo(0, -38); c.lineTo(28, 0); c.lineTo(0, 38); c.lineTo(-28, 0); c.closePath(); fill(mix(hue, '#ffffff', 0.6), mix(hue, '#000000', 0.25)); c.beginPath(); c.moveTo(-28, 0); c.lineTo(28, 0); c.stroke(); }
  else if (shape === 'triangle') { c.beginPath(); c.moveTo(0, -36); c.lineTo(32, 26); c.lineTo(-32, 26); c.closePath(); fill(mix(hue, '#ffffff', 0.5), mix(hue, '#000000', 0.2)); }
  else { c.beginPath(); c.arc(0, -8, 22, 0, TAU); fill(mix(hue, '#ffffff', 0.7), hue); c.fillStyle = '#556'; c.fillRect(-10, 12, 20, 14); }
};

ACTORS.bubble = (c, P, t) => {
  const pop = P.pop || 0, R = 78, hue = P.hue || '#9fd8ff', seed = P.seed || 1, bob = Math.sin(t * 0.9 + seed) * 6;
  if (pop < 0.35) {
    const sc = 1 + pop * 0.5, al = 1 - pop / 0.35; c.save(); c.translate(0, bob); c.scale(sc, sc); c.globalAlpha *= al;
    const g = c.createRadialGradient(-R * 0.3, -R * 0.35, R * 0.1, 0, 0, R); g.addColorStop(0, 'rgba(255,255,255,0.10)'); g.addColorStop(0.8, rgba(hue, 0.12)); g.addColorStop(1, rgba(hue, 0.5));
    c.fillStyle = g; c.beginPath(); c.arc(0, 0, R, 0, TAU); c.fill();
    c.lineWidth = 2.4; ['#ff8ad8', '#8affc8', '#8ab4ff'].forEach((cc, i) => { c.strokeStyle = rgba(cc, 0.35); c.beginPath(); c.arc(0, 0, R - 2 - i * 2, i * 2.1, i * 2.1 + 1.5); c.stroke(); });
    c.fillStyle = 'rgba(255,255,255,0.55)'; c.beginPath(); c.ellipse(-R * 0.38, -R * 0.42, R * 0.16, R * 0.08, -0.7, 0, TAU); c.fill();
    c.save(); c.scale(0.28, 0.28); c.translate(0, 120 + seed * 3); c.globalAlpha *= 0.85;
    lighthouseBody(c, { power: 0.3, tint: seed % 2 ? '#8ab4ff' : '#ff8ad8' }, t); c.restore(); c.restore();
  }
  if (pop > 0) { const u = clamp(pop); for (let i = 0; i < 14; i++) { const a = i / 14 * TAU, d = R * (1 + u * 1.3); c.strokeStyle = rgba(hue, (1 - u) * 0.8); c.lineWidth = 3; c.beginPath(); c.arc(Math.cos(a) * d * 0.9, bob + Math.sin(a) * d * 0.9, 8 * (1 - u * 0.5), a - 0.5, a + 0.5); c.stroke(); } }
};

ACTORS.pedestal = (c, P, t) => {
  const fill = P.fill || 0, kind = P.kind || 'orb', col = P.color || '#2ec4b6';
  const g = c.createLinearGradient(-50, 0, 50, 0); g.addColorStop(0, '#16213a'); g.addColorStop(0.5, '#2c3b60'); g.addColorStop(1, '#16213a');
  c.fillStyle = g; c.fillRect(-46, -20, 92, 20); c.fillRect(-32, -150, 64, 130); c.fillRect(-54, -172, 108, 24);
  c.strokeStyle = 'rgba(130,150,190,0.35)'; c.lineWidth = 2; c.strokeRect(-54, -172, 108, 24); c.strokeRect(-46, -20, 92, 20);
  const oy = -250 + Math.sin(t * 1.3) * 8;
  if (fill < 0.98) { c.save(); c.globalAlpha *= (1 - fill) * (0.35 + 0.25 * Math.sin(t * 2)); c.strokeStyle = col; c.setLineDash([8, 8]); c.lineWidth = 2; c.beginPath(); c.arc(0, oy, 42, 0, TAU); c.stroke(); c.restore(); }
  if (fill > 0.01) {
    c.save(); c.globalAlpha *= clamp(fill); c.translate(0, oy); c.scale(0.5 + 0.5 * EASE.back(clamp(fill)), 0.5 + 0.5 * EASE.back(clamp(fill))); glowAdd(c, 0, 0, 120, col, 0.5);
    if (kind === 'orb') { const og = c.createRadialGradient(-10, -12, 4, 0, 0, 44); og.addColorStop(0, '#ffffff'); og.addColorStop(0.4, mix(col, '#ffffff', 0.4)); og.addColorStop(1, mix(col, '#06101a', 0.5)); c.fillStyle = og; c.beginPath(); c.arc(0, 0, 44, 0, TAU); c.fill(); c.strokeStyle = 'rgba(255,255,255,0.4)'; c.lineWidth = 1.5; for (let i = 0; i < 3; i++) { c.beginPath(); c.ellipse(0, 0, 40, 14 + i * 8, t * 0.5 + i, 0, TAU); c.stroke(); } }
    else if (kind === 'eye') { c.strokeStyle = col; c.lineWidth = 4; c.fillStyle = 'rgba(8,16,28,0.9)'; c.beginPath(); c.moveTo(-58, 0); c.quadraticCurveTo(0, -46, 58, 0); c.quadraticCurveTo(0, 46, -58, 0); c.fill(); c.stroke(); const ex = Math.sin(t * 1.1) * 12; glowAdd(c, ex, 0, 40, col, 0.8); c.fillStyle = col; c.beginPath(); c.arc(ex, 0, 18, 0, TAU); c.fill(); c.fillStyle = '#050a12'; c.beginPath(); c.arc(ex, 0, 8, 0, TAU); c.fill(); }
    else if (kind === 'needle') { c.strokeStyle = col; c.lineWidth = 4; c.beginPath(); c.arc(0, 0, 44, 0, TAU); c.stroke(); const a = Math.sin(t * 0.9) * 0.5 - 0.6; c.save(); c.rotate(a); c.fillStyle = PAL.red; c.beginPath(); c.moveTo(0, -38); c.lineTo(7, 0); c.lineTo(-7, 0); c.closePath(); c.fill(); c.fillStyle = col; c.beginPath(); c.moveTo(0, 38); c.lineTo(7, 0); c.lineTo(-7, 0); c.closePath(); c.fill(); c.restore(); }
    else { c.fillStyle = '#efe8d6'; c.beginPath(); c.moveTo(0, 18); c.quadraticCurveTo(-30, 4, -58, 16); c.lineTo(-58, -26); c.quadraticCurveTo(-30, -38, 0, -22); c.quadraticCurveTo(30, -38, 58, -26); c.lineTo(58, 16); c.quadraticCurveTo(30, 4, 0, 18); c.fill(); c.strokeStyle = 'rgba(60,55,45,0.45)'; c.lineWidth = 2; for (let i = 0; i < 4; i++) { c.beginPath(); c.moveTo(-50, -16 + i * 8); c.lineTo(-8, -12 + i * 8); c.moveTo(8, -12 + i * 8); c.lineTo(50, -16 + i * 8); c.stroke(); } }
    c.restore();
  }
};

ACTORS.crystal = (c, P, t) => {
  const grow = P.grow === undefined ? 1 : P.grow, hue = P.hue || '#7fd4ff', R = 120 * grow, R2 = prng(P.seed || 4);
  glowAdd(c, 0, -R * 1.1, R * 3.2, hue, 0.2);
  const pts = []; const n = 7; for (let i = 0; i < n; i++) { const a = -Math.PI / 2 + i / n * TAU, r = R * (0.75 + R2() * 0.45); pts.push([Math.cos(a) * r, -R * 1.1 + Math.sin(a) * r * 1.2]); }
  const top = [0, -R * 2.5], bot = [0, 0];
  c.lineJoin = 'round';
  for (let i = 0; i < n; i++) { const a = pts[i], b = pts[(i + 1) % n]; const ang = Math.atan2(a[1] + R, a[0]), f = 0.5 + 0.5 * Math.sin(ang * 2 + t * 0.5);
    for (const apex of [top, bot]) { c.beginPath(); c.moveTo(apex[0], apex[1]); c.lineTo(a[0], a[1]); c.lineTo(b[0], b[1]); c.closePath(); const g = c.createLinearGradient(apex[0], apex[1], (a[0] + b[0]) / 2, (a[1] + b[1]) / 2);
      g.addColorStop(0, rgba(mix(hue, '#ffffff', 0.6 * f), 0.75)); g.addColorStop(1, rgba(mix(hue, '#5a3fd0', 0.7 - 0.4 * f), 0.5)); c.fillStyle = g; c.fill(); c.strokeStyle = rgba('#ffffff', 0.45); c.lineWidth = 1.6; c.stroke(); } }
  for (let k = 0; k < 3; k++) { const ph = fract(t * 0.18 + k / 3), gx = lerp(-R * 0.6, R * 0.6, ph), gy = -R * (0.6 + k * 0.5); glowAdd(c, gx, gy, 46, '#ffffff', 0.7 * Math.sin(ph * Math.PI)); }
};

ACTORS.gear = (c, P, t) => {
  const teeth = P.teeth || 12, R = P.R || 70, col = P.color || '#6f86b8', ph = (P.speed === undefined ? 0.4 : P.speed) * t + (P.phase || 0), warm = P.warm || 0;
  c.rotate(ph); c.beginPath();
  for (let i = 0; i < teeth; i++) { const a = i / teeth * TAU, w = TAU / teeth / 2; c.lineTo(Math.cos(a - w * 0.5) * R, Math.sin(a - w * 0.5) * R); c.lineTo(Math.cos(a - w * 0.3) * (R + 14), Math.sin(a - w * 0.3) * (R + 14)); c.lineTo(Math.cos(a + w * 0.3) * (R + 14), Math.sin(a + w * 0.3) * (R + 14)); c.lineTo(Math.cos(a + w * 0.5) * R, Math.sin(a + w * 0.5) * R); }
  c.closePath(); c.arc(0, 0, R * 0.38, 0, TAU, true);
  const g = c.createLinearGradient(-R, -R, R, R); g.addColorStop(0, mix(col, '#ffffff', 0.25)); g.addColorStop(1, mix(col, '#0a1020', 0.5)); c.fillStyle = g; c.fill('evenodd');
  c.strokeStyle = rgba(mix('#aab8d8', '#ffbf5a', warm), 0.8); c.lineWidth = 2; c.stroke();
  for (let i = 0; i < 5; i++) { const a = i / 5 * TAU; c.strokeStyle = rgba('#0a1020', 0.5); c.lineWidth = 8; c.beginPath(); c.moveTo(Math.cos(a) * R * 0.4, Math.sin(a) * R * 0.4); c.lineTo(Math.cos(a) * R * 0.85, Math.sin(a) * R * 0.85); c.stroke(); }
  if (warm > 0) glowAdd(c, 0, 0, R * 1.8, '#ffb25a', 0.25 * warm);
};

function strokePartial(c, pts, f) { // draw the first fraction f of a polyline
  let tot = 0; const seg = []; for (let i = 1; i < pts.length; i++) { const d = Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]); seg.push(d); tot += d; }
  let need = tot * clamp(f); c.beginPath(); c.moveTo(pts[0][0], pts[0][1]);
  for (let i = 1; i < pts.length && need > 0; i++) { const d = seg[i - 1]; if (need >= d) { c.lineTo(pts[i][0], pts[i][1]); need -= d; } else { const u = need / d; c.lineTo(pts[i - 1][0] + (pts[i][0] - pts[i - 1][0]) * u, pts[i - 1][1] + (pts[i][1] - pts[i - 1][1]) * u); need = 0; } }
  c.stroke();
}
ACTORS.blueprint = (c, P, t) => {
  const p = clamp(P.p === undefined ? 1 : P.p), kind = P.kind || 'bridge', col = P.color || '#5fb8e8', w = 560, h = 340;
  c.save(); c.globalAlpha *= 0.9; c.strokeStyle = rgba(col, 0.12); c.lineWidth = 1;
  for (let x = -w / 2; x <= w / 2; x += 28) { c.beginPath(); c.moveTo(x, -h / 2); c.lineTo(x, h / 2); c.stroke(); }
  for (let y = -h / 2; y <= h / 2; y += 28) { c.beginPath(); c.moveTo(-w / 2, y); c.lineTo(w / 2, y); c.stroke(); }
  c.restore(); c.lineCap = 'round'; c.lineJoin = 'round'; c.strokeStyle = rgba(col, 0.95); c.lineWidth = 3;
  const arc = (cx, cy, r, a0, a1) => { const o = []; for (let i = 0; i <= 40; i++) { const a = lerp(a0, a1, i / 40); o.push([cx + Math.cos(a) * r, cy + Math.sin(a) * r]); } return o; };
  if (kind === 'bridge') {
    const parts = [[[-250, 60], [250, 60]], arc(0, 120, 230, Math.PI * 1.08, Math.PI * 1.92), [[-250, 60], [-250, 140]], [[250, 60], [250, 140]], ...[-150, -75, 0, 75, 150].map((x) => [[x, 60], [x, 120 - Math.sqrt(Math.max(0, 230 * 230 - x * x)) + 120 - 120 + 0 + 0]])];
    parts.forEach((pl, i) => { const f = clamp(p * parts.length - i); if (f > 0) strokePartial(c, pl, f); });
    c.strokeStyle = rgba(col, 0.5); c.lineWidth = 1.5; if (p > 0.6) { strokePartial(c, [[-250, 170], [250, 170]], (p - 0.6) / 0.4); strokePartial(c, [[-250, 160], [-250, 180]], (p - 0.6) / 0.4); strokePartial(c, [[250, 160], [250, 180]], (p - 0.6) / 0.4); }
  } else if (kind === 'tower') {
    const parts = [[[-90, 150], [-50, -150], [50, -150], [90, 150], [-90, 150]], [[-60, 60], [60, 60]], [[-70, -40], [70, -40]], [[-55, -110], [55, -110]], [[-60, -150], [0, -210], [60, -150]]];
    parts.forEach((pl, i) => { const f = clamp(p * parts.length - i); if (f > 0) strokePartial(c, pl, f); });
  } else { // plan: rows of items that tick off one by one
    for (let i = 0; i < 5; i++) { const y = -130 + i * 62, f = clamp(p * 5 - i); if (f <= 0) continue; c.strokeStyle = rgba(col, 0.95); strokePartial(c, [[-240, y], [-200, y], [-200, y + 34], [-240, y + 34], [-240, y]], clamp(f * 2)); strokePartial(c, [[-170, y + 17], [-170 + 330 * (0.55 + (i * 0.13 % 0.4)), y + 17]], f);
      if (f > 0.7) { c.strokeStyle = rgba('#56c596', 1); c.lineWidth = 5; strokePartial(c, [[-236, y + 18], [-224, y + 30], [-203, y + 4]], (f - 0.7) / 0.3); c.lineWidth = 3; } }
  }
};

ACTORS.coin = (c, P, t) => {
  const R = 70, sp = P.spin === undefined ? t * 2.4 : P.spin, cw = Math.cos(sp), wd = Math.abs(cw) * R, thick = 12;
  glowAdd(c, 0, 0, 150, '#ffbf5a', 0.22 * (P.shine === undefined ? 1 : P.shine));
  c.fillStyle = '#8a5f12'; c.beginPath(); c.ellipse(0, thick / 2, wd, R, 0, 0, TAU); c.fill();
  const g = c.createRadialGradient(-wd * 0.3, -R * 0.35, 4, 0, 0, R); g.addColorStop(0, '#fff0b8'); g.addColorStop(0.55, '#e8b44a'); g.addColorStop(1, '#a5741a');
  c.fillStyle = g; c.beginPath(); c.ellipse(0, -thick / 2, wd, R, 0, 0, TAU); c.fill();
  c.strokeStyle = 'rgba(120,80,10,0.8)'; c.lineWidth = 3; c.beginPath(); c.ellipse(0, -thick / 2, wd * 0.8, R * 0.8, 0, 0, TAU); c.stroke();
  if (wd > 14) { c.save(); c.translate(0, -thick / 2); c.scale(wd / R, 1); c.fillStyle = 'rgba(120,80,10,0.75)'; c.beginPath(); for (let i = 0; i < 10; i++) { const a = -Math.PI / 2 + i / 10 * TAU, r = i % 2 ? 14 : 34; c.lineTo(Math.cos(a) * r, Math.sin(a) * r); } c.closePath(); c.fill(); c.restore(); }
};

ACTORS.lamps = (c, P, t) => {
  const st = P.states || [0, 0, 0], gap = P.gap || 190, n = st.length;
  for (let i = 0; i < n; i++) {
    const x = (i - (n - 1) / 2) * gap, s = clamp(st[i]), sw = Math.sin(t * 1.6 + i) * 0.05, col = mix('#d95d5d', '#56c596', s);
    c.save(); c.translate(x, 0); c.rotate(sw); c.strokeStyle = '#46567c'; c.lineWidth = 4; c.beginPath(); c.moveTo(0, -330); c.lineTo(0, -130); c.stroke();
    glowAdd(c, 0, -60, 150, col, 0.55); c.fillStyle = '#18233e'; c.beginPath(); c.roundRect(-36, -130, 72, 140, 18); c.fill();
    const g = c.createLinearGradient(0, -120, 0, 0); g.addColorStop(0, rgba(mix(col, '#ffffff', 0.5), 0.95)); g.addColorStop(1, rgba(col, 0.9)); c.fillStyle = g; c.beginPath(); c.roundRect(-26, -118, 52, 116, 12); c.fill();
    c.strokeStyle = 'rgba(8,12,22,0.8)'; c.lineWidth = 3; c.beginPath(); c.moveTo(-26, -60); c.lineTo(26, -60); c.stroke(); c.fillStyle = '#24365c'; c.fillRect(-42, -140, 84, 14); c.restore();
  }
};
