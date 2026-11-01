// World actors: sky, sea, mist, particles, lighthouse, oracle, ship, figure, rings, ribbon, grade.
// Local origin of every actor is its anchor point; the engine already applied x, y, s, r, flip.

ACTORS.sky = (c, P, t) => {
  const tone = P.tone || 0; // 0 deep night .. 1 dusk/dawn
  const g = c.createLinearGradient(0, -H, 0, H * 2);
  c.save(); c.setTransform(1, 0, 0, 1, 0, 0);
  const gg = c.createLinearGradient(0, 0, 0, H);
  gg.addColorStop(0, mix('#04060d', '#101a38', tone));
  gg.addColorStop(0.55, mix('#0a1226', '#3d3158', tone));
  gg.addColorStop(1, mix('#0f1d33', '#d68a3e', tone * 0.85));
  c.fillStyle = gg; c.fillRect(0, 0, W, H); c.restore();
  const n = Math.round(240 * (P.stars === undefined ? 1 : P.stars));
  const R = prng(11);
  for (let i = 0; i < n; i++) {
    const x = R() * W * 1.6 - W * 0.3, y = R() * H * 0.78 - H * 0.1, r = 0.4 + R() * 1.5, ph = R() * TAU, sp = 0.6 + R() * 2.2;
    const a = (0.25 + 0.75 * (0.5 + 0.5 * Math.sin(t * sp + ph))) * (1 - tone * 0.85);
    c.fillStyle = rgba(R() < 0.15 ? '#bfe9ff' : '#ffffff', a * 0.85);
    c.beginPath(); c.arc(x, y, r, 0, TAU); c.fill();
    if (r > 1.5) { c.strokeStyle = rgba('#ffffff', a * 0.35); c.lineWidth = 0.7; c.beginPath(); c.moveTo(x - r * 4, y); c.lineTo(x + r * 4, y); c.moveTo(x, y - r * 4); c.lineTo(x, y + r * 4); c.stroke(); }
  }
  if (P.moon) {
    const mx = P.mx === undefined ? 1480 : P.mx, my = P.my === undefined ? 190 : P.my, mr = 52 * (P.ms || 1);
    glowAdd(c, mx, my, mr * 5, '#bfe9ff', 0.28);
    const mg = c.createRadialGradient(mx - mr * 0.3, my - mr * 0.3, 2, mx, my, mr);
    mg.addColorStop(0, '#f6f4ec'); mg.addColorStop(1, '#c9d2dc');
    c.fillStyle = mg; c.beginPath(); c.arc(mx, my, mr, 0, TAU); c.fill();
    c.fillStyle = 'rgba(120,135,155,0.28)';
    [[-14, -8, 11], [12, 10, 15], [-4, 20, 7]].forEach(([dx, dy, rr]) => { c.beginPath(); c.arc(mx + dx * (mr / 52), my + dy * (mr / 52), rr * (mr / 52), 0, TAU); c.fill(); });
    if (P.phase) { // crescent: dark disc slides across
      c.save(); c.beginPath(); c.arc(mx, my, mr + 1, 0, TAU); c.clip();
      c.fillStyle = mix('#04060d', '#101a38', tone); c.beginPath(); c.arc(mx + P.phase * mr * 2, my, mr * 1.02, 0, TAU); c.fill(); c.restore();
    }
  }
};

ACTORS.sea = (c, P, t) => {
  const hy = P.hy === undefined ? 720 : P.hy, amp = P.amp === undefined ? 9 : P.amp, sp = P.speed === undefined ? 0.5 : P.speed, tone = P.tone || 0;
  c.save(); c.setTransform(1, 0, 0, 1, 0, 0);
  const sg = c.createLinearGradient(0, hy - 6, 0, H);
  sg.addColorStop(0, mix('#14263d', '#7a5a52', tone)); sg.addColorStop(0.35, mix('#0b1830', '#2c2740', tone)); sg.addColorStop(1, mix('#050a16', '#150f22', tone));
  c.fillStyle = sg; c.fillRect(0, hy - 2, W, H - hy + 2); c.restore();
  // horizon haze
  glowAdd(c, W / 2, hy, 900, mix('#2a4a78', '#e6a45a', tone), 0.12);
  const L = 7;
  for (let i = L - 1; i >= 0; i--) {
    const by = hy + 14 + i * ((H - hy) / L) * 0.95, f = 0.004 + i * 0.0017, a = amp * (0.4 + i * 0.28);
    c.beginPath(); c.moveTo(-40, H + 20);
    for (let x = -40; x <= W + 40; x += 14) {
      const y = by + Math.sin(x * f + t * sp * (0.7 + i * 0.12) + i * 1.9) * a + Math.sin(x * f * 2.3 - t * sp * 0.9 + i) * a * 0.38;
      c.lineTo(x, y);
    }
    c.lineTo(W + 40, H + 20); c.closePath();
    c.fillStyle = rgba(mix('#0c1b33', '#2e2540', tone), 0.55 + i * 0.05); c.fill();
    c.strokeStyle = rgba(mix('#6fa8d8', '#f0b070', tone), 0.05 + i * 0.012); c.lineWidth = 1.2; c.stroke();
  }
  if (P.refl) { // shimmering light path (moon or beam) on the water
    const rx = P.rx === undefined ? W / 2 : P.rx, col = P.rcol || '#bfe9ff', R = prng(5);
    for (let k = 0; k < 46; k++) {
      const y = hy + 10 + Math.pow(k / 46, 1.4) * (H - hy - 20), wdt = (18 + k * 3.4) * (0.4 + 0.6 * R());
      const a = P.refl * (0.55 - k / 90) * (0.5 + 0.5 * Math.sin(t * 2.2 + k * 1.3));
      c.fillStyle = rgba(col, Math.max(0, a)); c.fillRect(rx - wdt / 2 + Math.sin(t + k) * 6, y, wdt, 2.2);
    }
  }
};

ACTORS.mist = (c, P, t) => {
  const col = P.color || '#9fb4cc', a = P.a === undefined ? 0.16 : P.a, n = P.n || 7, sp = P.speed === undefined ? 1 : P.speed, wdt = P.w || 520;
  for (let i = 0; i < n; i++) {
    const x = ((i * 380 + t * sp * (14 + (i % 3) * 7)) % (W + 900)) - 450, y = Math.sin(i * 2.1) * 26;
    c.save(); c.translate(x, y); c.scale(1, 0.3); glow(c, 0, 0, wdt, col, a * (0.6 + 0.4 * Math.sin(t * 0.3 + i))); c.restore();
  }
};

ACTORS.particles = (c, P, t) => {
  const n = P.n || 60, w = P.w || W, h = P.h || H, col = P.color || '#bfe9ff', sp = P.speed === undefined ? 1 : P.speed, dir = (P.dir === undefined ? -90 : P.dir) * Math.PI / 180, R = prng(P.seed || 3);
  for (let i = 0; i < n; i++) {
    const bx = R() * w, by = R() * h, v = (8 + R() * 22) * sp, ph = R();
    const x = ((bx + Math.cos(dir) * v * t + Math.sin(t * 0.7 + i) * 14) % w + w) % w, y = ((by + Math.sin(dir) * v * t) % h + h) % h;
    const a = (0.25 + 0.5 * Math.sin(t * (0.8 + ph) + i)) ** 2 * (P.a === undefined ? 0.9 : P.a), r = (P.size || 1.8) * (0.5 + R());
    glowAdd(c, x - w / 2, y - h / 2, r * 5, col, a * 0.5);
    c.fillStyle = rgba(col, a); c.beginPath(); c.arc(x - w / 2, y - h / 2, r, 0, TAU); c.fill();
  }
};

ACTORS.grade = (c, P) => { // vignette + tint, drawn in screen space
  c.save(); c.setTransform(1, 0, 0, 1, 0, 0);
  const g = c.createRadialGradient(W / 2, H / 2, H * 0.35, W / 2, H / 2, H * 0.95);
  g.addColorStop(0, 'rgba(0,0,0,0)'); g.addColorStop(1, `rgba(2,3,8,${P.v === undefined ? 0.6 : P.v})`);
  c.fillStyle = g; c.fillRect(0, 0, W, H);
  if (P.tint) { c.fillStyle = rgba(P.tint, P.ta === undefined ? 0.06 : P.ta); c.fillRect(0, 0, W, H); }
  c.restore();
};

// ---- lighthouse -------------------------------------------------------------------------------------
function lighthouseBody(c, P, t) {
  const tint = P.tint, dark = P.dark;
  const bodyL = tint ? mix('#0a0818', tint, 0.35) : '#1d2a45', bodyR = tint ? mix('#0a0818', tint, 0.7) : '#44577e';
  const g = c.createLinearGradient(-60, 0, 60, 0); g.addColorStop(0, bodyL); g.addColorStop(1, bodyR);
  c.fillStyle = g; c.beginPath(); c.moveTo(-62, 0); c.lineTo(-40, -300); c.lineTo(40, -300); c.lineTo(62, 0); c.closePath(); c.fill();
  // bands
  c.save(); c.beginPath(); c.moveTo(-62, 0); c.lineTo(-40, -300); c.lineTo(40, -300); c.lineTo(62, 0); c.closePath(); c.clip();
  for (let i = 0; i < 4; i++) { c.fillStyle = tint ? rgba(tint, 0.25) : 'rgba(232,225,205,0.82)'; c.fillRect(-70, -300 + i * 80 + 12, 140, 36); }
  c.restore();
  // base rock
  c.fillStyle = tint ? mix('#08060f', tint, 0.2) : '#101827'; c.beginPath(); c.moveTo(-150, 14); c.quadraticCurveTo(-90, -26, -60, -8); c.lineTo(70, -8); c.quadraticCurveTo(110, -30, 170, 14); c.closePath(); c.fill();
  // gallery, lantern room, roof
  c.fillStyle = tint ? mix('#0a0818', tint, 0.5) : '#2b3a5c'; c.fillRect(-56, -312, 112, 14);
  const lp = P.power === undefined ? 0 : P.power;
  c.fillStyle = lp > 0 ? mix('#2a2f44', '#ffe2a0', clamp(lp)) : '#222a3d'; c.fillRect(-30, -352, 60, 42);
  c.fillStyle = tint ? mix('#0a0818', tint, 0.6) : '#1a2440';
  c.fillRect(-32, -355, 4, 46); c.fillRect(28, -355, 4, 46); c.fillRect(-2, -355, 4, 46);
  c.beginPath(); c.moveTo(-40, -352); c.lineTo(0, -392); c.lineTo(40, -352); c.closePath(); c.fillStyle = tint ? mix('#0a0818', tint, 0.8) : '#34466e'; c.fill();
  c.fillStyle = '#34466e'; c.fillRect(-1.5, -410, 3, 20);
  // door and window
  c.fillStyle = 'rgba(8,12,22,0.85)'; c.fillRect(-9, -52, 18, 52);
  c.fillStyle = lp > 0 ? rgba('#ffd98a', 0.35 + 0.5 * lp) : 'rgba(20,30,50,0.9)'; c.fillRect(-7, -170, 14, 24);
}
ACTORS.lighthouse = (c, P, t) => {
  const lp = P.power === undefined ? 0 : P.power, bm = P.beam === undefined ? lp : P.beam, foc = P.focus === undefined ? 0.5 : P.focus;
  const ang = (P.aim !== undefined ? P.aim : Math.sin(t * (P.sweepSpeed || 0.5)) * (P.sweep || 10)) * Math.PI / 180;
  if (bm > 0.01) {
    const ha = lerp(0.5, 0.03, foc), L = 2000, col = P.bcol || '#ffd98a';
    for (const dir of [0, Math.PI]) {
      const k = dir ? 0.4 : 1;
      c.save(); c.translate(0, -331); c.rotate(ang + dir); c.globalCompositeOperation = 'lighter';
      for (let q = 0; q < 12; q++) { // stacked cones of falling opacity give the beam a soft edge
        const w = ha * (1 - q * 0.075), g = c.createLinearGradient(0, 0, L, 0);
        g.addColorStop(0, rgba(col, 0.115 * bm * k)); g.addColorStop(0.35, rgba(col, 0.045 * bm * k)); g.addColorStop(1, rgba(col, 0));
        c.fillStyle = g; c.beginPath(); c.moveTo(0, 0); c.lineTo(L, -Math.tan(w) * L); c.lineTo(L, Math.tan(w) * L); c.closePath(); c.fill();
      }
      if (foc > 0.45) { const g = c.createLinearGradient(0, 0, L, 0); g.addColorStop(0, rgba('#fff3d0', 0.5 * bm * k * (foc - 0.45))); g.addColorStop(1, rgba('#fff3d0', 0)); c.strokeStyle = g; c.lineWidth = 4; c.beginPath(); c.moveTo(0, 0); c.lineTo(L, 0); c.stroke(); }
      c.restore();
    }
  }
  lighthouseBody(c, P, t);
  if (lp > 0.01) { glowAdd(c, 0, -331, 170 * lp + 30, P.bcol || '#ffd98a', 0.85 * lp); glowAdd(c, 0, -331, 60, '#fff3d0', 0.9 * lp); }
};

// ---- oracle: a faceless being of light --------------------------------------------------------------
ACTORS.oracle = (c, P, t) => {
  const col = P.color || '#bfe9ff', calm = P.calm === undefined ? 0.5 : P.calm, g = P.glow === undefined ? 1 : P.glow, sp = P.speak || 0, sw = (1.2 - calm) * 14;
  glowAdd(c, 0, -250, 420, col, 0.16 * g);
  // flowing cape: three translucent veils with a wavy hem
  for (let k = 0; k < 3; k++) {
    const ph = t * (0.5 + k * 0.17) + k * 1.3, half = 120 + k * 26, hem = 0;
    c.beginPath(); c.moveTo(-26, -330);
    c.bezierCurveTo(-40, -240, -half * 0.8 + Math.sin(ph) * sw, -120, -half + Math.sin(ph + 1) * sw, hem);
    for (let x = -half; x <= half; x += 14) c.lineTo(x + Math.sin(ph + x * 0.03) * sw * 0.4, hem + Math.sin(ph * 1.7 + x * 0.05) * 9);
    c.bezierCurveTo(half * 0.8 + Math.sin(ph + 2) * sw, -120, 40, -240, 26, -330); c.closePath();
    const gr = c.createLinearGradient(0, -330, 0, 0); gr.addColorStop(0, rgba('#ffffff', 0.62 * g)); gr.addColorStop(0.5, rgba(col, 0.28 * g)); gr.addColorStop(1, rgba(col, 0));
    c.fillStyle = gr; c.fill();
  }
  // shoulders and torso
  const tg = c.createLinearGradient(0, -340, 0, -140); tg.addColorStop(0, rgba('#ffffff', 0.9 * g)); tg.addColorStop(1, rgba(col, 0.2 * g));
  c.fillStyle = tg; c.beginPath(); c.moveTo(-58, -300); c.quadraticCurveTo(0, -352, 58, -300); c.quadraticCurveTo(34, -200, 24, -140); c.lineTo(-24, -140); c.quadraticCurveTo(-34, -200, -58, -300); c.closePath(); c.fill();
  // head of pure light: no face
  glowAdd(c, 0, -392, 100, '#ffffff', 0.85 * g);
  const hgr = c.createRadialGradient(-6, -400, 2, 0, -392, 36); hgr.addColorStop(0, '#ffffff'); hgr.addColorStop(1, rgba(col, 0.9)); c.fillStyle = hgr; c.beginPath(); c.ellipse(0, -392, 28, 36, 0, 0, TAU); c.fill();
  // halo behind the head
  for (let k = 0; k < 2; k++) { c.save(); c.translate(0, -396); c.rotate(t * 0.3 * (k ? -1 : 1)); c.scale(0.45 + k * 0.12, 1); c.strokeStyle = rgba(col, (0.55 - k * 0.18) * g); c.lineWidth = 2; c.setLineDash([22, 12]); c.beginPath(); c.arc(0, 0, 78 + k * 22, 0, TAU); c.stroke(); c.restore(); }
  // two hands of light
  const hy = -240 + Math.sin(t * 1.2) * 6;
  for (const sx of [-1, 1]) { const hx = sx * (92 + sp * 24 * Math.sin(t * 3)); c.strokeStyle = rgba(col, 0.5 * g); c.lineWidth = 6; c.lineCap = 'round'; c.beginPath(); c.moveTo(sx * 46, -290); c.quadraticCurveTo(sx * 90, -280, hx, hy); c.stroke(); glowAdd(c, hx, hy, 54, '#ffffff', 0.7 * g); }
  // speech: rings leave the head
  if (sp > 0) for (let k = 0; k < 4; k++) { const ph = fract(t * 0.5 + k / 4); c.strokeStyle = rgba(col, (1 - ph) * 0.5 * sp); c.lineWidth = 2; c.beginPath(); c.arc(0, -392, 50 + ph * 340, 0, TAU); c.stroke(); }
  const R = prng(9);
  for (let i = 0; i < 28; i++) { const a = R() * TAU, r = 40 + R() * 150, y = -R() * 430, px = Math.cos(a + t * 0.3) * r * (0.4 + 0.6 * (-y) / 430), py = y - ((t * 14 + i * 20) % 90); c.fillStyle = rgba(col, 0.3 + 0.4 * Math.sin(t * 2 + i)); c.beginPath(); c.arc(px, py, 1.5, 0, TAU); c.fill(); }
};

// ---- ship, figure, rings, ribbon --------------------------------------------------------------------
ACTORS.ship = (c, P, t) => {
  const bob = Math.sin(t * 0.9 + (P.seed || 0)) * 5, tilt = Math.sin(t * 0.7 + (P.seed || 0)) * 0.05;
  c.translate(0, bob); c.rotate(tilt);
  c.fillStyle = '#0c1424'; c.beginPath(); c.moveTo(-52, 0); c.lineTo(52, 0); c.lineTo(38, 18); c.lineTo(-38, 18); c.closePath(); c.fill();
  c.fillStyle = '#131d34'; c.beginPath(); c.moveTo(0, -4); c.lineTo(0, -92); c.lineTo(44, -6); c.closePath(); c.fill();
  c.beginPath(); c.moveTo(-4, -8); c.lineTo(-4, -78); c.lineTo(-36, -8); c.closePath(); c.fillStyle = '#18243f'; c.fill();
  c.fillStyle = '#0c1424'; c.fillRect(-1, -100, 2, 100);
  const lit = P.lit === undefined ? 1 : P.lit;
  glowAdd(c, 0, -102, 40, '#ffd98a', 0.6 * lit);
};
ACTORS.figure = (c, P, t) => {
  const col = P.color || '#d8d4c8', pose = P.pose || 'stand', w = pose === 'walk' ? Math.sin(t * 5) : 0;
  c.fillStyle = col; c.strokeStyle = col; c.lineCap = 'round';
  // cloak
  c.beginPath(); c.moveTo(0, -150); c.quadraticCurveTo(-34, -110, -40, -4); c.lineTo(40, -4); c.quadraticCurveTo(34, -110, 0, -150); c.closePath();
  const g = c.createLinearGradient(0, -150, 0, 0); g.addColorStop(0, rgba(col, 0.95)); g.addColorStop(1, rgba(col, 0.55)); c.fillStyle = g; c.fill();
  c.beginPath(); c.arc(0, -166, 15, 0, TAU); c.fillStyle = col; c.fill();
  c.lineWidth = 6;
  if (pose === 'ask') { c.beginPath(); c.moveTo(14, -120); c.lineTo(46, -168 + Math.sin(t * 2) * 4); c.stroke(); }
  if (pose === 'look') { c.beginPath(); c.moveTo(14, -120); c.lineTo(52, -128); c.stroke(); }
  if (pose === 'walk') { c.lineWidth = 7; c.beginPath(); c.moveTo(-10, -4); c.lineTo(-10 + w * 16, 26); c.moveTo(10, -4); c.lineTo(10 - w * 16, 26); c.stroke(); }
  if (pose === 'walk' || pose === 'stand') { c.lineWidth = 3; c.strokeStyle = rgba(col, 0.7); c.beginPath(); c.moveTo(-44, 24); c.lineTo(-38, -138); c.stroke(); }
};
ACTORS.rings = (c, P, t) => {
  const n = P.n || 4, col = P.color || '#bfe9ff', R = P.R || 300, sp = P.speed === undefined ? 0.5 : P.speed, a = P.a === undefined ? 0.5 : P.a, r0 = P.r0 || 20, squash = P.squash || 1;
  c.save(); c.scale(1, squash);
  for (let k = 0; k < n; k++) { const ph = fract(t * sp - k / n + (P.phase || 0)); c.strokeStyle = rgba(col, (1 - ph) * a); c.lineWidth = P.w || 2; c.beginPath(); c.arc(0, 0, r0 + ph * R, 0, TAU); c.stroke(); }
  c.restore();
};
ACTORS.ribbon = (c, P, t) => {
  // flowing ribbon of light from (x0,y0) to (x1,y1); p = head 0..1, q = tail 0..1
  const x0 = P.x0 || 0, y0 = P.y0 || 0, x1 = P.x1 === undefined ? 600 : P.x1, y1 = P.y1 === undefined ? 0 : P.y1;
  const p = clamp(P.p === undefined ? 0 : P.p), q = clamp(P.q === undefined ? Math.max(0, p - 0.3) : P.q), col = P.color || '#ffd98a', seed = P.seed || 1, R = prng(seed * 17);
  const a1 = (R() - 0.5) * 420, a2 = (R() - 0.5) * 420, wv = P.wave === undefined ? 1 : P.wave;
  const pt = (u) => { const m = 1 - u; const bx = m * m * m * x0 + 3 * m * m * u * (x0 + (x1 - x0) * 0.3) + 3 * m * u * u * (x0 + (x1 - x0) * 0.7) + u * u * u * x1;
    const by = m * m * m * y0 + 3 * m * m * u * (y0 + a1) + 3 * m * u * u * (y1 + a2) + u * u * u * y1; return [bx, by + Math.sin(u * 14 + t * 2.4 + seed) * 10 * wv * Math.sin(u * Math.PI)]; };
  c.save(); c.globalCompositeOperation = 'lighter'; c.lineCap = 'round';
  const N = 60;
  for (let i = 0; i < N; i++) {
    const u0 = lerp(q, p, i / N), u1 = lerp(q, p, (i + 1) / N); if (u1 <= u0) continue;
    const a = Math.pow((i + 1) / N, 1.6), [ax, ay] = pt(u0), [bx, by] = pt(u1);
    c.strokeStyle = rgba(col, 0.75 * a * (P.a === undefined ? 1 : P.a)); c.lineWidth = (P.w || 9) * a + 0.6; c.beginPath(); c.moveTo(ax, ay); c.lineTo(bx, by); c.stroke();
  }
  c.restore(); // no glowing head: a lone bright point would read as a focus marker
};
