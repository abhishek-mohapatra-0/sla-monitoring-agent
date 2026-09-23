/* Tiny SVG chart kit for the SLA dashboard - no external libraries. */
const C = {
  s1: '#2a78d6', s2: '#eb6834', ink: '#0b0b0b', ink2: '#52514e', muted: '#898781', grid: '#e1e0d9',
  base: '#c3c2b7', surface: '#fcfcfb', grey: '#a8a7a0',
  good: '#0ca30c', warn: '#fab219', crit: '#d03b3b', goodtext: '#006300', warntext: '#8a6100'
};
const NS = 'http://www.w3.org/2000/svg';
const pct = (v, d = 1) => v == null ? '–' : (v * 100).toFixed(d) + '%';
const num = v => v == null ? '–' : Math.round(v).toLocaleString('en-IN');
const fix = (v, d = 1) => v == null ? '–' : Number(v).toFixed(d);

function status(s) {
  if (s === 'On target') return ['▲', 'On target', C.goodtext];
  if (s === 'Watch') return ['●', 'Watch', C.warntext];
  if (s === 'Below target') return ['▼', 'Below target', C.crit];
  return ['', '', C.ink2];
}

function el(p, t, a = {}, txt) {
  const e = document.createElementNS(NS, t);
  for (const k in a) e.setAttribute(k, a[k]);
  if (txt !== undefined) e.textContent = txt;
  p.appendChild(e);
  return e;
}

function svgIn(box) {
  box.innerHTML = '';
  const W = Math.max(box.clientWidth, 200), H = +box.dataset.h || 240;
  const svg = el(box, 'svg', { width: W, height: H, viewBox: `0 0 ${W} ${H}` });
  return [svg, W, H];
}

/* ---------- tooltip */
const tip = () => document.getElementById('tip');
function showTip(ev, title, rows) {
  const t = tip();
  t.innerHTML = `<div class="t">${title}</div>` + rows.map(([k, v]) => `<div class="r"><span>${k}</span><b>${v}</b></div>`).join('');
  t.style.display = 'block';
  const x = ev.clientX + 14, y = ev.clientY + 14, w = t.offsetWidth, h = t.offsetHeight;
  t.style.left = (x + w > innerWidth ? ev.clientX - w - 10 : x) + 'px';
  t.style.top = (y + h > innerHeight ? ev.clientY - h - 10 : y) + 'px';
}
function hideTip() { tip().style.display = 'none'; }
function hover(node, title, rows) {
  node.addEventListener('mousemove', e => showTip(e, title, typeof rows === 'function' ? rows() : rows));
  node.addEventListener('mouseleave', hideTip);
  node.style.cursor = 'default';
}

function yTicks(svg, l, r, W, y, ticks, fmt) {
  ticks.forEach(v => {
    el(svg, 'line', { x1: l, x2: W - r, y1: y(v), y2: y(v), stroke: v === ticks[0] ? C.base : C.grid });
    el(svg, 'text', { x: l - 7, y: y(v) + 3.5, 'text-anchor': 'end', 'font-size': 11, fill: C.muted }, fmt(v));
  });
}
function roundTop(x, y, w, h, r = 3) { // bar with rounded data-end on top, anchored at baseline
  r = Math.min(r, w / 2, h);
  return `M${x},${y + h} V${y + r} a${r},${r} 0 0 1 ${r},-${r} H${x + w - r} a${r},${r} 0 0 1 ${r},${r} V${y + h} Z`;
}
function roundRight(x, y, w, h, r = 4) {
  r = Math.min(r, h / 2, w);
  return `M${x},${y} H${x + w - r} a${r},${r} 0 0 1 ${r},${r} V${y + h - r} a${r},${r} 0 0 1 -${r},${r} H${x} Z`;
}

/* ---------- line chart with crosshair */
function lineChart(box, { labels, series, yMin, yMax, yTicksAt, fmt = pct, annotate = [], xEvery = 1, tipTitle }) {
  const [svg, W, H] = svgIn(box);
  const l = 44, r = 14, t = 10, b = 26, n = labels.length;
  if (!n) return;
  const x = i => n === 1 ? (l + W - r) / 2 : l + (W - l - r) * i / (n - 1);
  const y = v => t + (H - t - b) * (1 - (v - yMin) / (yMax - yMin));
  yTicks(svg, l, r, W, y, yTicksAt, v => fmt(v, 0));
  labels.forEach((lb, i) => { if (i % xEvery === 0 || i === n - 1)
    el(svg, 'text', { x: x(i), y: H - 7, 'text-anchor': 'middle', 'font-size': 11, fill: C.muted }, lb); });
  series.forEach(s => {
    const pts = s.values.map((v, i) => v == null ? null : [x(i), y(Math.max(yMin, Math.min(yMax, v)))]);
    let d = '', pen = false;
    pts.forEach(p => { if (!p) { pen = false; return; } d += (pen ? 'L' : 'M') + p[0] + ',' + p[1]; pen = true; });
    el(svg, 'path', { d, fill: 'none', stroke: s.color, 'stroke-width': s.width || 2, 'stroke-linejoin': 'round',
      'stroke-dasharray': s.dash ? '5 4' : 'none' });
    if (s.markers) pts.forEach(p => p && el(svg, 'circle', { cx: p[0], cy: p[1], r: 3.5, fill: s.color, stroke: C.surface, 'stroke-width': 2 }));
  });
  annotate.forEach(a => {
    const v = series[0].values[a.i]; if (v == null) return;
    el(svg, 'text', { x: x(a.i) + (a.dx || 8), y: y(v) + (a.dy || 4), 'font-size': 11.5, 'font-weight': 700, fill: C.ink,
      'text-anchor': a.anchor || 'start' }, a.text);
  });
  // crosshair + tooltip
  const cross = el(svg, 'line', { y1: t, y2: H - b, stroke: C.base, 'stroke-dasharray': '3 3', visibility: 'hidden' });
  const hit = el(svg, 'rect', { x: l, y: t, width: W - l - r, height: H - t - b, fill: 'transparent' });
  hit.addEventListener('mousemove', e => {
    const bb = svg.getBoundingClientRect();
    const i = Math.max(0, Math.min(n - 1, Math.round((e.clientX - bb.left - l) / ((W - l - r) / Math.max(1, n - 1)))));
    cross.setAttribute('x1', x(i)); cross.setAttribute('x2', x(i)); cross.setAttribute('visibility', 'visible');
    showTip(e, tipTitle ? tipTitle(i) : labels[i], series.map(s => [s.name, fmt(s.values[i])]));
  });
  hit.addEventListener('mouseleave', () => { cross.setAttribute('visibility', 'hidden'); hideTip(); });
}

/* ---------- horizontal bars with target tick (bullet) */
function bulletBars(box, rows) {
  const [svg, W, H] = svgIn(box);
  const l = 40, r = 88, t = 8, b = 24, n = rows.length;
  if (!n) return;
  const rowH = (H - t - b) / n, bh = Math.min(28, rowH * .5);
  const x = v => l + (W - l - r) * v;
  [0, .25, .5, .75, 1].forEach(v => {
    el(svg, 'line', { x1: x(v), x2: x(v), y1: t, y2: H - b, stroke: v ? C.grid : C.base });
    el(svg, 'text', { x: x(v), y: H - 6, 'text-anchor': 'middle', 'font-size': 11, fill: C.muted }, (v * 100) + '%');
  });
  rows.forEach((d, i) => {
    const yy = t + i * rowH + (rowH - bh) / 2, st = status(d.status);
    el(svg, 'text', { x: l - 10, y: yy + bh / 2 + 4, 'text-anchor': 'end', 'font-size': 12.5, 'font-weight': 700, fill: C.ink2 }, d.label);
    const bar = el(svg, 'path', { d: roundRight(x(0), yy, Math.max(0, x(d.value || 0) - x(0)), bh), fill: C.s1 });
    if (d.target != null) el(svg, 'line', { x1: x(d.target), x2: x(d.target), y1: yy - 6, y2: yy + bh + 6, stroke: C.ink, 'stroke-width': 2.5 });
    el(svg, 'text', { x: W - r + 10, y: yy + bh / 2 + 4, 'font-size': 12.5, 'font-weight': 700, fill: C.ink }, pct(d.value));
    el(svg, 'text', { x: W - 8, y: yy + bh / 2 + 4, 'text-anchor': 'end', 'font-size': 11, fill: st[2] }, st[0]);
    const hitR = el(svg, 'rect', { x: 0, y: t + i * rowH, width: W, height: rowH, fill: 'transparent' });
    hover(hitR, d.label, [['Resolution SLA', pct(d.value)], ['Target', pct(d.target)], ['Status', st[1] || '–'], ['Tickets', num(d.total)]]);
  });
}

/* ---------- grouped columns */
function groupedColumns(box, { labels, series, fmt = num, yFmt, labelMaxOf = null, xEvery = 1 }) {
  const [svg, W, H] = svgIn(box);
  const l = 44, r = 10, t = 22, b = 26, n = labels.length;
  if (!n) return;
  const mx = Math.max(1, ...series.flatMap(s => s.values.map(v => v || 0)));
  const step = niceStep(mx / 4), top = Math.ceil(mx / step) * step;
  const y = v => t + (H - t - b) * (1 - v / top);
  const ticks = []; for (let v = 0; v <= top + 1e-9; v += step) ticks.push(v);
  yTicks(svg, l, r, W, y, ticks, yFmt || (v => v >= 1000 ? (v / 1000) + 'k' : v));
  const bw = (W - l - r) / n, k = series.length, w = Math.min(34, bw * .72 / k);
  labels.forEach((lb, i) => {
    const x0 = l + i * bw + (bw - (w * k + 2 * (k - 1))) / 2;
    series.forEach((s, j) => {
      const v = s.values[i] || 0, xx = x0 + j * (w + 2);
      el(svg, 'path', { d: roundTop(xx, y(v), w, y(0) - y(v)), fill: s.color });
    });
    if (i % xEvery === 0 || i === n - 1)
      el(svg, 'text', { x: l + i * bw + bw / 2, y: H - 7, 'text-anchor': 'middle', 'font-size': 11, fill: C.muted }, lb);
    const hitR = el(svg, 'rect', { x: l + i * bw, y: t, width: bw, height: H - t - b, fill: 'transparent' });
    hover(hitR, lb, series.map(s => [s.name, fmt(s.values[i])]));
  });
  if (labelMaxOf != null) {
    const vals = series[labelMaxOf].values, i = vals.indexOf(Math.max(...vals));
    const x0 = l + i * bw + (bw - (w * k + 2 * (k - 1))) / 2;
    el(svg, 'text', { x: x0 + (w * k) / 2, y: y(vals[i]) - 6, 'text-anchor': 'middle', 'font-size': 11.5, 'font-weight': 700, fill: C.ink }, fmt(vals[i]));
  }
}
function niceStep(raw) {
  const p = Math.pow(10, Math.floor(Math.log10(raw))), f = raw / p;
  return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10) * p;
}

/* ---------- simple columns with value labels */
function columns(box, { labels, values, color = C.s1, fmt = num, yFmt, max, tipRows }) {
  const [svg, W, H] = svgIn(box);
  const l = 44, r = 10, t = 22, b = 26, n = labels.length;
  const mx = max || Math.max(1, ...values.map(v => v || 0));
  const step = max ? max / 4 : niceStep(mx / 4), top = max || Math.ceil(mx / step) * step;
  const y = v => t + (H - t - b) * (1 - v / top);
  const ticks = []; for (let v = 0; v <= top + 1e-9; v += step) ticks.push(v);
  yTicks(svg, l, r, W, y, ticks, yFmt || (v => v));
  const bw = (W - l - r) / n, w = Math.min(64, bw * .55);
  labels.forEach((lb, i) => {
    const v = values[i] || 0, xx = l + i * bw + (bw - w) / 2;
    el(svg, 'path', { d: roundTop(xx, y(v), w, y(0) - y(v), 4), fill: color });
    el(svg, 'text', { x: xx + w / 2, y: y(v) - 6, 'text-anchor': 'middle', 'font-size': 12, 'font-weight': 700, fill: C.ink }, fmt(values[i]));
    el(svg, 'text', { x: xx + w / 2, y: H - 7, 'text-anchor': 'middle', 'font-size': 11.5, fill: C.ink2 }, lb);
    const hitR = el(svg, 'rect', { x: l + i * bw, y: t, width: bw, height: H - t - b, fill: 'transparent' });
    hover(hitR, lb, tipRows ? tipRows(i) : [['Value', fmt(values[i])]]);
  });
}

/* ---------- stacked horizontal bars */
function stackedBarsH(box, { labels, series }) {
  const [svg, W, H] = svgIn(box);
  const l = 130, r = 40, t = 6, b = 24, n = labels.length;
  if (!n) { svg.innerHTML = ''; el(svg, 'text', { x: W / 2, y: H / 2, 'text-anchor': 'middle', fill: C.muted }, 'No open tickets'); return; }
  const totals = labels.map((_, i) => series.reduce((a, s) => a + (s.values[i] || 0), 0));
  const mx = Math.max(1, ...totals), step = niceStep(mx / 4), top = Math.ceil(mx / step) * step;
  const x = v => l + (W - l - r) * v / top;
  for (let v = 0; v <= top + 1e-9; v += step) {
    el(svg, 'line', { x1: x(v), x2: x(v), y1: t, y2: H - b, stroke: v ? C.grid : C.base });
    el(svg, 'text', { x: x(v), y: H - 6, 'text-anchor': 'middle', 'font-size': 11, fill: C.muted }, v);
  }
  const rowH = (H - t - b) / n, bh = Math.min(22, rowH * .62);
  labels.forEach((lb, i) => {
    const yy = t + i * rowH + (rowH - bh) / 2;
    el(svg, 'text', { x: l - 10, y: yy + bh / 2 + 4, 'text-anchor': 'end', 'font-size': 12, fill: C.ink2 }, lb);
    let acc = 0;
    series.forEach((s, j) => {
      const v = s.values[i] || 0; if (!v) return;
      const x0 = x(acc), w = x(acc + v) - x0 - (j < series.length - 1 ? 2 : 0);
      el(svg, 'rect', { x: x0, y: yy, width: Math.max(1, w), height: bh, fill: s.color, rx: 2 });
      acc += v;
    });
    el(svg, 'text', { x: x(totals[i]) + 6, y: yy + bh / 2 + 4, 'font-size': 11.5, 'font-weight': 700, fill: C.ink }, totals[i]);
    const hitR = el(svg, 'rect', { x: 0, y: t + i * rowH, width: W, height: rowH, fill: 'transparent' });
    hover(hitR, lb, [...series.map(s => [s.name, s.values[i] || 0]), ['Total open', totals[i]]]);
  });
}

/* ---------- clickable horizontal bars (breakdown) */
function hbars(box, rows, { valueKey, fmt, sub, onClick, color = C.s1 }) {
  box.dataset.h = Math.max(120, rows.length * 30 + 10);
  const [svg, W, H] = svgIn(box);
  const l = 150, r = 120, t = 4, n = rows.length;
  if (!n) { el(svg, 'text', { x: W / 2, y: 40, 'text-anchor': 'middle', fill: C.muted }, 'No breaches here'); return; }
  const mx = Math.max(...rows.map(d => d[valueKey] || 0), 1);
  const x = v => l + (W - l - r) * v / mx, rowH = 30, bh = 18;
  rows.forEach((d, i) => {
    const yy = t + i * rowH + (rowH - bh) / 2;
    el(svg, 'text', { x: l - 10, y: yy + bh / 2 + 4, 'text-anchor': 'end', 'font-size': 12, fill: C.ink2 }, d.value);
    el(svg, 'path', { d: roundRight(l, yy, Math.max(1, x(d[valueKey] || 0) - l), bh), fill: color });
    el(svg, 'text', { x: x(d[valueKey] || 0) + 7, y: yy + bh / 2 + 4, 'font-size': 11.5, fill: C.ink },
      fmt(d[valueKey]) + (sub ? '  ' : ''));
    if (sub) el(svg, 'text', { x: W - 6, y: yy + bh / 2 + 4, 'text-anchor': 'end', 'font-size': 11, fill: C.ink2 }, sub(d));
    const hitR = el(svg, 'rect', { x: 0, y: t + i * rowH, width: W, height: rowH, fill: 'transparent' });
    hover(hitR, d.value, [['Breaches', num(d.breaches)], ['Breach rate', pct(d.breach_rate)], ['Tickets measured', num(d.measured)]]);
    if (onClick) { hitR.style.cursor = 'pointer'; hitR.addEventListener('click', () => { hideTip(); onClick(d); }); }
  });
}

/* ---------- scatter */
function scatter(box, pts, { refY, xLabel, yLabel, onClick }) {
  const [svg, W, H] = svgIn(box);
  const l = 48, r = 14, t = 10, b = 34;
  const xs = pts.map(p => p.x), ys = pts.map(p => p.y).filter(v => v != null);
  if (!pts.length) return;
  const xMax = niceStep(Math.max(...xs) / 4) * Math.ceil(Math.max(...xs) / niceStep(Math.max(...xs) / 4));
  const yMin = Math.max(0, Math.floor((Math.min(...ys, refY || 1) - .05) * 10) / 10), yMax = 1;
  const x = v => l + (W - l - r) * v / xMax, y = v => t + (H - t - b) * (1 - (v - yMin) / (yMax - yMin));
  const tk = []; for (let v = yMin; v <= yMax + 1e-9; v += .1) tk.push(+v.toFixed(2));
  yTicks(svg, l, r, W, y, tk, v => (v * 100).toFixed(0) + '%');
  const xs4 = xMax / 4;
  for (let v = 0; v <= xMax + 1e-9; v += xs4)
    el(svg, 'text', { x: x(v), y: H - 18, 'text-anchor': 'middle', 'font-size': 11, fill: C.muted }, num(v));
  el(svg, 'text', { x: (l + W - r) / 2, y: H - 3, 'text-anchor': 'middle', 'font-size': 11, fill: C.ink2 }, xLabel);
  if (refY != null) {
    el(svg, 'line', { x1: l, x2: W - r, y1: y(refY), y2: y(refY), stroke: C.ink2, 'stroke-dasharray': '5 4', 'stroke-width': 1.5 });
    el(svg, 'text', { x: W - r, y: y(refY) - 5, 'text-anchor': 'end', 'font-size': 10.5, fill: C.ink2 }, 'target ' + pct(refY));
  }
  pts.forEach(p => {
    if (p.y == null) return;
    const c = el(svg, 'circle', { cx: x(p.x), cy: y(p.y), r: 5, fill: p.color || C.s1, stroke: C.surface, 'stroke-width': 2, 'fill-opacity': .9 });
    const hitC = el(svg, 'circle', { cx: x(p.x), cy: y(p.y), r: 10, fill: 'transparent' });
    hover(hitC, p.label, p.tip);
    if (onClick) { hitC.style.cursor = 'pointer'; hitC.addEventListener('click', () => onClick(p)); }
  });
}

/* ---------- heatmap (single-hue sequential, light = low) */
function heatmap(box, { rows, cols, values, counts }) {
  const [svg, W, H] = svgIn(box);
  const l = 40, r = 6, t = 18, b = 4, nr = rows.length, nc = cols.length;
  const cw = (W - l - r) / nc, ch = (H - t - b) / nr;
  const ramp = ['#f3f7fd', '#cde2fb', '#9ec5f4', '#6da7ec', '#3987e5', '#256abf', '#184f95'];
  const vmax = Math.max(...values.flat().filter(v => v != null), .01);
  const col = v => v == null ? '#f0efec' : ramp[Math.min(ramp.length - 1, Math.floor(v / vmax * (ramp.length - .001)))];
  cols.forEach((c, j) => el(svg, 'text', { x: l + j * cw + cw / 2, y: 12, 'text-anchor': 'middle', 'font-size': 10, fill: C.muted }, c));
  rows.forEach((rw, i) => {
    el(svg, 'text', { x: l - 8, y: t + i * ch + ch / 2 + 4, 'text-anchor': 'end', 'font-size': 11.5, fill: C.ink2 }, rw);
    cols.forEach((c, j) => {
      const v = values[i][j], fill = col(v);
      const rc = el(svg, 'rect', { x: l + j * cw + 1, y: t + i * ch + 1, width: cw - 2, height: ch - 2, fill, rx: 2 });
      if (cw > 30) el(svg, 'text', { x: l + j * cw + cw / 2, y: t + i * ch + ch / 2 + 4, 'text-anchor': 'middle', 'font-size': 10,
        fill: ramp.indexOf(fill) >= 4 ? '#fff' : C.ink }, v == null ? '' : Math.round(v * 100));
      hover(rc, `${rw} ${c}:00`, [['Response breach', pct(v)], ['Tickets', num(counts[i][j])]]);
    });
  });
}
