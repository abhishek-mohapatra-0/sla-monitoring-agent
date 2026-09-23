/* SLA dashboard front-end: filters, pages, rendering. */
const S = { page: 'overview', meta: null, cache: {}, agent: null, path: [], dim: 'Team', openTeams: new Set() };
const $ = id => document.getElementById(id);
const TITLES = { overview: 'SLA Performance Overview', queue: 'Live Queue - what needs attention now',
  people: 'Team & Agent Performance', root: 'Breach Root Cause - why are we breaching?', detail: 'Ticket Detail' };

let SEQ = 0;   // drop responses from older requests so fast filter clicks never show stale data
async function get(url) {
  const my = SEQ, r = await fetch(url);
  if (!r.ok) throw new Error(url);
  const j = await r.json();
  if (my !== SEQ) throw new Error('stale');
  return j;
}

function qs(extra = {}) {
  const p = new URLSearchParams();
  const [s, e] = dateRange();
  if (s) p.set('start', s); if (e) p.set('end', e);
  ['priority', 'team', 'channel'].forEach(k => { const v = $('f' + k[0].toUpperCase() + k.slice(1)).value; if (v) p.set(k, v); });
  for (const k in extra) if (extra[k] != null) p.set(k, extra[k]);
  return p.toString();
}

function dateRange() {
  const v = $('fDate').value, max = new Date(S.meta.max_date);
  const iso = d => d.toISOString().slice(0, 10);
  const back = (m, days) => { const d = new Date(max); if (m) d.setMonth(d.getMonth() - m); if (days) d.setDate(d.getDate() - days); d.setDate(d.getDate() + 1); return iso(d); };
  if (v === '12m') return [back(12), S.meta.max_date];
  if (v === '6m') return [back(6), S.meta.max_date];
  if (v === '3m') return [back(3), S.meta.max_date];
  if (v === '30d') return [back(0, 30), S.meta.max_date];
  if (v === 'custom') return [$('fStart').value || null, $('fEnd').value || null];
  return [null, null];
}

function rangeText() {
  const [s, e] = dateRange();
  const f = d => new Date(d).toLocaleString('en', { month: 'short', year: 'numeric' });
  return `${f(s || S.meta.min_date)} – ${f(e || S.meta.max_date)}`;
}

/* ================================================================ KPI tile */
function tile(label, value, sub) {
  return `<div class="card k"><div class="lab">${label}</div><div class="val">${value}</div><div class="sub">${sub}</div></div>`;
}

/* ================================================================ OVERVIEW */
async function renderOverview() {
  const d = await get('/api/overview?' + qs()), k = d.kpis, st = status(k.status);
  $('ovKpis').innerHTML = [
    tile('Resolution SLA %', pct(k.res_sla), k.status ? `<span class="st" style="color:${st[2]}">${st[0]} ${st[1].replace(' target', '')}</span> · ${k.gap_pts > 0 ? '+' : ''}${fix(k.gap_pts)} pts vs ${pct(k.target)}` : '–'),
    tile('Response SLA %', pct(k.resp_sla), `${num(k.resp_breaches)} first-response breaches`),
    tile('Total tickets', num(k.total), `${num(k.breaches)} resolution breaches`),
    tile('Open now', num(k.open), `<span class="st" style="color:${k.overdue ? C.crit : C.ink2}">${k.overdue} overdue</span> · ${k.at_risk} at risk`),
    tile('MTTR', k.mttr_hrs == null ? '–' : fix(k.mttr_hrs) + ' h', `MTTA ${fix(k.mtta_min, 0)} min`),
    tile('CSAT', k.csat == null ? '–' : fix(k.csat, 2) + ' / 5', `Reopen rate ${pct(k.reopen_rate)}`)].join('');

  const M = d.monthly, labels = M.map(m => m.label), res = M.map(m => m.res_sla);
  const lo = Math.min(...res.filter(v => v != null), ...M.map(m => m.target || 1));
  const yMin = Math.max(0, Math.floor((lo - .03) * 10) / 10);
  const ticks = []; for (let v = yMin; v <= 1.0001; v += .1) ticks.push(+v.toFixed(2));
  const minI = res.indexOf(Math.min(...res.filter(v => v != null))), last = M.length - 1;
  const ann = [];
  if (M.length > 1 && minI !== last && res[minI] < (M[minI].target || 1) - .05)
    ann.push({ i: minI, text: pct(res[minI]), anchor: minI > M.length - 3 ? 'end' : 'start', dx: minI > M.length - 3 ? -8 : 8 });
  if (last >= 0) ann.push({ i: last, text: pct(res[last]) + (M[last].mtd ? ' (MTD)' : ''), anchor: 'end', dx: -4, dy: 18 });
  lineChart($('ovTrend'), { labels, yMin, yMax: 1, yTicksAt: ticks, annotate: ann,
    series: [{ name: 'Resolution SLA %', values: res, color: C.s1, markers: true },
             { name: 'Target', values: M.map(m => m.target), color: C.ink2, dash: true, width: 1.5 }],
    tipTitle: i => M[i].month + (M[i].mtd ? ' (month to date)' : '') });

  bulletBars($('ovPrio'), d.priority.map(p => ({ label: p.priority, value: p.res_sla, target: p.target, status: p.status, total: p.total })));

  groupedColumns($('ovCvr'), { labels, labelMaxOf: 0,
    series: [{ name: 'Created', values: M.map(m => m.created), color: C.s1 },
             { name: 'Resolved', values: M.map(m => m.resolved), color: C.s2 }] });

  let h = '<tr><th>Team</th><th>Tickets</th><th>SLA %</th><th>Target</th><th>Gap</th><th>MTTR (h)</th><th>Multi-hop</th></tr>';
  d.teams.forEach(t => { const s = status(t.status);
    h += `<tr class="click" data-team="${t.key}"><td>${t.key}</td><td>${num(t.total)}</td><td><b>${pct(t.res_sla)}</b></td><td>${pct(t.target)}</td>
      <td style="color:${s[2]};font-weight:700">${s[0]} ${t.gap_pts > 0 ? '+' : ''}${fix(t.gap_pts)}</td><td>${fix(t.mttr_hrs)}</td><td>${pct(t.multi_hop)}</td></tr>`; });
  $('ovTeams').innerHTML = h;
  $('ovTeams').querySelectorAll('tr.click').forEach(tr => tr.onclick = () => { $('fTeam').value = tr.dataset.team; refresh(); });
}

/* ================================================================ QUEUE */
async function renderQueue() {
  const d = await get('/api/queue?' + qs()), k = d.kpis;
  $('qKpis').innerHTML = [
    tile('Open tickets', num(k.open), 'Unresolved at the snapshot time'),
    tile('Overdue', `<span style="color:${k.overdue ? C.crit : C.ink}">${num(k.overdue)}</span>`, 'Breached and still open'),
    tile('At risk', num(k.at_risk), '75%+ of SLA time used, not yet breached'),
    tile('Avg age of open tickets', k.avg_open_age_hrs == null ? '–' : fix(k.avg_open_age_hrs) + ' h', 'Hours since the ticket was created')].join('');
  stackedBarsH($('qTeams'), { labels: d.by_team.map(r => r.team), series: [
    { name: 'Overdue', values: d.by_team.map(r => r['Open - Overdue']), color: C.crit },
    { name: 'At risk', values: d.by_team.map(r => r['Open - At Risk']), color: C.warn },
    { name: 'On track', values: d.by_team.map(r => r['Open - On Track']), color: C.s1 }] });
  columns($('qAging'), { labels: d.aging.map(a => a.bucket), values: d.aging.map(a => a.count),
    tipRows: i => [['Open tickets', d.aging[i].count]] });
  let h = '<tr><th>Ticket</th><th class="l">Priority</th><th class="l">Team</th><th class="l">Agent</th><th class="l">Sub-category</th><th class="l">Status</th><th class="l">SLA status</th><th>Created</th><th>Resolution due</th><th>Hours to breach</th></tr>';
  d.tickets.forEach(t => {
    const c = t.sla === 'Open - Overdue' ? C.crit : t.sla === 'Open - At Risk' ? C.warntext : C.ink2;
    h += `<tr class="click" data-id="${t.id}"><td>${t.id}</td><td class="l">${t.priority}</td><td class="l">${t.team}</td><td class="l">${t.agent}</td><td class="l">${t.sub}</td>
      <td class="l">${t.status}</td><td class="l" style="color:${c};font-weight:600">${t.sla.replace('Open - ', '')}</td><td>${t.created}</td><td>${t.due}</td>
      <td class="${t.hours_to_breach < 0 ? 'neg' : ''}">${fix(t.hours_to_breach)}</td></tr>`; });
  $('qTable').innerHTML = d.tickets.length ? h : '<tr><td class="empty">No open tickets for this filter</td></tr>';
  $('qTable').querySelectorAll('tr.click').forEach(tr => tr.onclick = () => openTicket(tr.dataset.id));
}

/* ================================================================ PEOPLE */
async function renderPeople() {
  const d = await get('/api/people?' + qs({ agent: S.agent }));
  const row = (r, cls, attr) => { const s = status(r.status);
    return `<tr class="${cls}" ${attr}><td>${r.key}</td><td>${num(r.total)}</td><td><b>${pct(r.res_sla)}</b></td>
      <td style="color:${s[2]};font-weight:700">${s[0]} ${r.gap_pts > 0 ? '+' : ''}${fix(r.gap_pts)}</td><td>${fix(r.mttr_hrs)}</td>
      <td>${fix(r.avg_reassign, 2)}</td><td>${pct(r.reopen_rate)}</td><td>${fix(r.csat, 2)}</td></tr>`; };
  let h = '<tr><th>Team / agent</th><th>Tickets</th><th>SLA %</th><th>Gap</th><th>MTTR h</th><th>Reassign</th><th>Reopen %</th><th>CSAT</th></tr>';
  d.teams.forEach(t => {
    const open = S.openTeams.has(t.key);
    h += row(t, 'click team' + (open ? ' open' : ''), `data-team="${t.key}"`);
    if (open) t.agents.forEach(a => h += row(a, 'click agent' + (S.agent === a.key ? ' sel' : ''), `data-agent="${a.key}"`));
  });
  $('pTable').innerHTML = h;
  $('pTable').querySelectorAll('tr.team').forEach(tr => tr.onclick = () => {
    const k = tr.dataset.team; S.openTeams.has(k) ? S.openTeams.delete(k) : S.openTeams.add(k); renderPeople(); });
  $('pTable').querySelectorAll('tr.agent').forEach(tr => tr.onclick = () => {
    S.agent = S.agent === tr.dataset.agent ? null : tr.dataset.agent; renderPeople(); });

  const tgt = d.kpis.target;
  scatter($('pScatter'), d.scatter.map(p => ({ x: p.total, y: p.res_sla, label: p.agent,
    color: S.agent && S.agent !== p.agent ? '#cde2fb' : C.s1,
    tip: [['Team', p.team], ['Tickets', num(p.total)], ['Resolution SLA', pct(p.res_sla)]] })),
    { refY: tgt, xLabel: 'Tickets handled', onClick: p => { S.agent = S.agent === p.label ? null : p.label; renderPeople(); } });

  $('pTrendTitle').textContent = 'Reopen rate by month - ' + (S.agent || 'all agents');
  const vals = d.trend.map(t => t.reopen_rate), mx = Math.max(.08, ...vals.filter(v => v != null));
  const top = Math.ceil(mx * 50) / 50, stp = top > .12 ? .04 : .02, ticks = []; for (let v = 0; v <= top + 1e-9; v += stp) ticks.push(+v.toFixed(2));
  lineChart($('pTrend'), { labels: d.trend.map(t => t.label), yMin: 0, yMax: top, yTicksAt: ticks,
    series: [{ name: 'Reopen rate', values: vals, color: C.s1, markers: true }], xEvery: 2 });
}

/* ================================================================ ROOT CAUSE */
async function renderRoot() {
  const d = await get('/api/rootcause?' + qs());
  columns($('rBands'), { labels: d.bands.map(b => b.band === '3+' ? '3+ hand-offs' : b.band + (b.band === '1' ? ' hand-off' : ' hand-offs')),
    values: d.bands.map(b => b.breach_rate), fmt: v => pct(v), yFmt: v => (v * 100).toFixed(0) + '%', max: 1,
    tipRows: i => [['Breach rate', pct(d.bands[i].breach_rate)], ['Tickets', num(d.bands[i].tickets)]] });
  heatmap($('rHeat'), { rows: d.days, cols: [...Array(24).keys()].map(h => String(h).padStart(2, '0')), values: d.heat, counts: d.heat_n });
  const R = d.rolling, lab = R.map(r => r.date);
  const vs = R.map(r => r.v).filter(v => v != null), lo = Math.max(0, Math.floor((Math.min(...vs) - .02) * 10) / 10);
  const tk = []; for (let v = lo; v <= 1.0001; v += .1) tk.push(+v.toFixed(2));
  const xl = lab.map(s => { const dt = new Date(s); return dt.getDate() === 1 ? dt.toLocaleString('en', { month: 'short' }) : ''; });
  lineChart($('rRoll'), { labels: xl, yMin: lo, yMax: 1, yTicksAt: tk, xEvery: 1,
    series: [{ name: '30-day SLA', values: R.map(r => r.v), color: C.s1 }],
    tipTitle: i => new Date(lab[i]).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }) });
  // x labels: only month starts; lineChart prints every label so blank ones are fine
  await renderTree();
}

async function renderTree() {
  const path = S.path.map(([k, v]) => `${k}:${v}`).join('|');
  const d = await get('/api/breakdown?' + qs({ path, dim: S.dim }));
  const used = new Set(S.path.map(p => p[0]));
  $('rCrumbs').innerHTML = `<span class="crumb root" data-i="-1">All breaches (${num(d.path.length ? null : d.breaches)})</span>` +
    S.path.map(([k, v], i) => `› <span class="crumb" data-i="${i}">${k}: ${v}</span>`).join(' ') +
    (S.path.length ? ` <span class="hint">${num(d.breaches)} breaches · ${pct(d.breaches / Math.max(1, d.measured))} breach rate</span>` : '');
  if (!S.path.length) $('rCrumbs').querySelector('.root').textContent = `All breaches (${num(d.breaches)})`;
  $('rCrumbs').querySelectorAll('.crumb').forEach(c => c.onclick = () => { S.path = S.path.slice(0, +c.dataset.i + 1); pickNextDim(); renderTree(); });
  $('rDims').innerHTML = S.meta.breakdown_dims.map(k =>
    `<span class="dim ${k === S.dim ? 'on' : ''} ${used.has(k) ? 'used' : ''}" data-k="${k}">${k}</span>`).join('');
  $('rDims').querySelectorAll('.dim').forEach(c => c.onclick = () => { S.dim = c.dataset.k; renderTree(); });
  hbars($('rTree'), d.rows.slice(0, 12), { valueKey: 'breaches', fmt: num,
    sub: r => pct(r.breach_rate) + ' rate',
    onClick: r => { S.path.push([S.dim, r.value]); pickNextDim(); renderTree(); } });
}
function pickNextDim() {
  const order = ['Team', 'Priority', 'Reassignments', 'SubCategory', 'Shift', 'Weekday', 'Channel', 'Agent', 'Category'];
  const used = new Set(S.path.map(p => p[0]));
  S.dim = order.find(k => !used.has(k)) || 'Agent';
}

/* ================================================================ DETAIL */
async function openTicket(id) { $('tId').value = id; switchPage('detail'); }
async function renderDetail() {
  const id = $('tId').value.trim();
  if (!id) return;
  const r = await fetch('/api/ticket/' + encodeURIComponent(id));
  if (!r.ok) { $('tBody').innerHTML = `<div class="empty">No ticket called ${id}</div>`; return; }
  const t = await r.json();
  const slaC = /Breached|Overdue/.test(t.sla) ? C.crit : /Risk/.test(t.sla) ? C.warntext : C.goodtext;
  const fact = (l, v) => `<div class="fact"><div class="lab">${l}</div><div class="v">${v}</div></div>`;
  $('tBody').innerHTML = `
    <h2 style="font-size:18px">${t.id} <span class="pill" style="background:${slaC}1a;color:${slaC}">${t.sla}</span></h2>
    <div class="cap">${t.category} › ${t.sub} · via ${t.channel}</div>
    <div class="facts">${fact('Priority', t.priority)}${fact('Team', t.team)}${fact('Agent', t.agent)}${fact('Status', t.status)}
      ${fact('Hours to breach', t.hours_to_breach == null ? '–' : `<span class="${t.hours_to_breach < 0 ? 'neg' : ''}">${fix(t.hours_to_breach)}</span>`)}</div>
    <div class="facts">${fact('First response', t.response_mins == null ? '–' : fix(t.response_mins) + ' min <span style="color:#898781;font-weight:400">/ ' + t.response_target_mins + ' target</span>')}
      ${fact('Resolution', t.resolution_hrs == null ? 'Open' : fix(t.resolution_hrs) + ' h <span style="color:#898781;font-weight:400">/ ' + t.resolution_target_hrs + ' target</span>')}
      ${fact('Reassignments', t.reassign)}${fact('Reopened', t.reopened ? 'Yes' : 'No')}${fact('CSAT', t.csat == null ? 'No survey' : t.csat + ' / 5')}</div>
    <div class="timeline">${t.timeline.map(s => `<div class="step"><div class="dot ${s.at == null ? 'none' : s.ok === false ? 'miss' : ''}"></div>
      <div class="s">${s.step}${s.ok === true ? ' ✓ in time' : s.ok === false ? ' ✕ late' : ''}</div><div class="a">${s.at || (s.ok === false ? 'Not yet - SLA breached' : '—')}</div></div>`).join('')}</div>`;
}

/* ================================================================ shell */
const RENDER = { overview: renderOverview, queue: renderQueue, people: renderPeople, root: renderRoot, detail: renderDetail };
function switchPage(p) {
  S.page = p;
  document.querySelectorAll('.page').forEach(s => s.classList.toggle('on', s.id === 'p-' + p));
  document.querySelectorAll('#tabs div').forEach(t => t.classList.toggle('on', t.dataset.p === p));
  $('pageTitle').textContent = TITLES[p];
  document.querySelector('.slicers').style.visibility = p === 'detail' ? 'hidden' : 'visible';
  refresh();
}
async function refresh() {
  $('asof').textContent = `Data as of ${S.meta.as_of} · ${rangeText()}`;
  SEQ++;
  try { await RENDER[S.page](); } catch (e) { if (e.message !== 'stale') console.error(e); }
}

async function init() {
  S.meta = await get('/api/meta');
  const fill = (id, arr) => arr.forEach(v => $(id).insertAdjacentHTML('beforeend', `<option>${v}</option>`));
  fill('fPriority', S.meta.priorities); fill('fTeam', S.meta.teams); fill('fChannel', S.meta.channels);
  $('fStart').value = S.meta.min_date; $('fEnd').value = S.meta.max_date;
  $('fDate').onchange = () => { $('customBox').classList.toggle('on', $('fDate').value === 'custom'); refresh(); };
  ['fPriority', 'fTeam', 'fChannel', 'fStart', 'fEnd'].forEach(id => $(id).onchange = () => { S.path = []; S.dim = 'Team'; refresh(); });
  $('reset').onclick = () => { ['fPriority', 'fTeam', 'fChannel'].forEach(id => $(id).value = ''); $('fDate').value = 'all';
    $('customBox').classList.remove('on'); S.agent = null; S.path = []; S.dim = 'Team'; refresh(); };
  document.querySelectorAll('#tabs div').forEach(t => t.onclick = () => switchPage(t.dataset.p));
  $('tGo').onclick = renderDetail; $('tId').onkeydown = e => { if (e.key === 'Enter') renderDetail(); };
  let rt; addEventListener('resize', () => { clearTimeout(rt); rt = setTimeout(refresh, 200); });
  refresh();
}
init();
