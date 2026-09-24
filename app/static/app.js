/* SLA dashboard front-end: filters, pages, rendering. */
const S = { page: 'overview', meta: null, cache: {}, agent: null, path: [], dim: 'Team', openTeams: new Set() };
const $ = id => document.getElementById(id);
const TITLES = { overview: 'SLA Performance Overview', queue: 'Live Queue - what needs attention now',
  people: 'Team & Agent Performance', root: 'Breach Root Cause - why are we breaching?', detail: 'Ticket Detail', agent: 'AI Agent - ask, explain, act' };

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


/* ================================================================ AI agent */
const A = { history: [], busy: false, loaded: false };
const SUGGEST = ['How are we doing today?', 'Why did SLA drop in March?', 'Which tickets will breach next?',
  'Which agents need support?', 'Why is Network Ops breaching?', 'Why do night tickets miss response SLA?',
  'Compare August vs July', 'Tell me about INC1061815'];
const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

function md(src) {                       // small Markdown renderer for agent answers
  const inline = t => esc(t).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>').replace(/(^|[^*])\*(?!\s)(.+?)\*(?!\*)/g, '$1<i>$2</i>')
    .replace(/`(.+?)`/g, '<code>$1</code>').replace(/&lt;sub&gt;(.*?)&lt;\/sub&gt;/g, '<sub>$1</sub>')
    .replace(/\b(INC\d{7})\b/g, '<a href="#" class="tk" data-t="$1">$1</a>');
  const lines = src.split('\n'), out = []; let i = 0;
  while (i < lines.length) {
    const l = lines[i].trim();
    if (l.startsWith('|') && i + 1 < lines.length && /^\|?\s*:?-{2,}/.test(lines[i + 1].trim())) {
      const row = r => r.trim().replace(/^\||\|$/g, '').split('|').map(c => c.trim());
      const head = row(l); i += 2; const body = [];
      while (i < lines.length && lines[i].trim().startsWith('|')) body.push(row(lines[i++]));
      out.push('<table><tr>' + head.map(h => `<th>${inline(h)}</th>`).join('') + '</tr>' +
        body.map(r => '<tr>' + r.map(c => `<td>${inline(c)}</td>`).join('') + '</tr>').join('') + '</table>');
      continue;
    }
    const ul = l.match(/^[-*•]\s+(.*)/), ol = l.match(/^\d+[.)]\s+(.*)/);
    if (ul || ol) {
      const tag = ul ? 'ul' : 'ol', re = ul ? /^[-*•]\s+(.*)/ : /^\d+[.)]\s+(.*)/, items = [];
      while (i < lines.length && re.test(lines[i].trim())) items.push(lines[i++].trim().match(re)[1]);
      out.push(`<${tag}>` + items.map(x => `<li>${inline(x)}</li>`).join('') + `</${tag}>`); continue;
    }
    if (/^#{1,4}\s/.test(l)) out.push(`<p><b>${inline(l.replace(/^#+\s*/, ''))}</b></p>`);
    else if (l) out.push(`<p>${inline(l)}</p>`);
    i++;
  }
  return out.join('');
}

function addMsg(role, html, tools) {
  const div = document.createElement('div');
  div.className = 'msg ' + role;
  div.innerHTML = html + (tools && tools.length ? `<div class="tools">tools used: ${tools.map(t =>
    `<span title="${esc(JSON.stringify(t.args || {}))}">${esc(t.tool)}</span>`).join('')}</div>` : '');
  $('aMsgs').appendChild(div); $('aMsgs').scrollTop = $('aMsgs').scrollHeight;
  div.querySelectorAll('a.tk').forEach(a => a.onclick = e => { e.preventDefault(); openTicket(a.dataset.t); });
  return div;
}

async function ask(q) {
  q = (q || '').trim(); if (!q || A.busy) return;
  A.busy = true; $('aSend').disabled = true; $('aInput').value = '';
  addMsg('u', esc(q));
  const wait = addMsg('a think', 'Thinking… (choosing tools and running the analysis)');
  try {
    const r = await fetch('/api/agent/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: q, history: A.history }) });
    const j = await r.json(); wait.remove();
    addMsg('a', md(j.answer || j.error || 'No answer'), j.tools);
    A.history.push({ role: 'user', content: q }, { role: 'assistant', content: j.answer || '' });
    A.history = A.history.slice(-10);
  } catch (e) { wait.remove(); addMsg('a', 'Something went wrong: ' + esc(e.message)); }
  A.busy = false; $('aSend').disabled = false; $('aInput').focus();
}

async function renderAgent() {
  if (!A.loaded) {
    A.loaded = true;
    $('aChips').innerHTML = SUGGEST.map(s => `<button type="button">${esc(s)}</button>`).join('');
    $('aChips').querySelectorAll('button').forEach(b => b.onclick = () => ask(b.textContent));
    $('aForm').onsubmit = e => { e.preventDefault(); ask($('aInput').value); };
    $('aReport').onclick = makeReport;
    const st = await (await fetch('/api/agent/status')).json();
    $('aMode').textContent = st.mode; $('aMode').classList.toggle('off', !st.llm);
    addMsg('a', md(`Hi! I'm your **SLA Monitoring Agent**. I watch ${S.meta ? 'the ticket data' : 'the data'} as of **${S.meta.as_of}**, ` +
      `explain breaches, flag people and process issues and predict which open tickets will breach.\n\n` +
      (st.llm ? `Running on **${st.mode}**.` : `Running in **offline mode** (rule-based, no API key). Add a free Groq or Gemini key in \`app/.env\` for free-form questions.`) +
      `\n\nTry a suggestion below or ask your own question.`));
    const [b, rk] = await Promise.all([fetch('/api/agent/briefing').then(r => r.json()), fetch('/api/agent/risk').then(r => r.json())]);
    renderBrief(b); renderRisk(rk);
  }
}

function renderBrief(h) {
  const c = h.current, [si, , sc] = status(c.status), pc = v => v == null ? '—' : (v * 100).toFixed(1) + '%';
  $('aBriefCap').textContent = `Last ${h.window.days} days (${h.window.start} to ${h.window.end}) · ${h.counts.critical} critical · ${h.counts.warning} warnings · ${h.counts.info} info`;
  const rc = h.root_cause.path.map(p => `${esc(p.dimension)} <b>${esc(p.value)}</b> (${pc(p.breach_rate)})`).join(' → ');
  $('aBrief').innerHTML = `<div class="head">Resolution SLA <b>${pc(c.res_sla)}</b> vs ${pc(c.target)} target ·
      <span class="st" style="color:${sc}">${si} ${esc(c.status)}</span> · ${c.open} open, <span class="neg">${c.overdue} overdue</span></div>
    ${rc ? `<div class="rcpath">Root cause: ${rc}</div>` : ''}` +
    h.alerts.map(a => `<div class="alert"><span class="sev ${a.severity}">${a.severity}</span>
      <div><b>${esc(a.title)}</b><div class="d">${esc(a.detail)}</div></div></div>`).join('');
}

function renderRisk(r) {
  const m = r.model;
  $('aRiskCap').textContent = `Gradient boosting · ROC AUC ${m.roc_auc} · PR AUC ${m.pr_auc} (base rate ${(m.base_rate * 100).toFixed(1)}%) on ${m.test_period} · click a row`;
  $('aRisk').innerHTML = '<tr><th>Ticket</th><th class="l">Team · agent</th><th>Hours left</th><th>Risk</th><th class="l" style="width:42%">Why</th></tr>' +
    r.tickets.map(t => `<tr class="click" data-id="${t.ticket}"><td>${t.ticket}<div style="color:var(--muted);font-size:10.5px">${t.priority}</div></td>
      <td class="l">${esc(t.team)}<div style="color:var(--muted);font-size:10.5px">${esc(t.agent)}</div></td><td>${t.hours_to_breach}</td>
      <td class="neg">${Math.round(t.breach_risk * 100)}%</td><td class="l" style="white-space:normal;color:var(--ink2);font-size:11px">${esc(t.why.slice(0, 2).join('; '))}</td></tr>`).join('');
  $('aRisk').querySelectorAll('tr.click').forEach(tr => tr.onclick = () => openTicket(tr.dataset.id));
}

async function makeReport() {
  $('aReport').disabled = true; $('aReportOut').textContent = 'Building report…';
  try {
    const j = await (await fetch('/api/agent/report?send=1', { method: 'POST' })).json();
    const sent = Object.entries(j.sent || {}).map(([k, v]) => `${k}: ${esc(v)}`).join(' · ');
    $('aReportOut').innerHTML = `✓ <a href="${j.html_url}" target="_blank">Open ${esc(j.file)}</a> · saved in the <code>reports</code> folder${sent ? ' · ' + sent : ''}`;
  } catch (e) { $('aReportOut').textContent = 'Failed: ' + e.message; }
  $('aReport').disabled = false;
}

/* ================================================================ shell */
const RENDER = { overview: renderOverview, queue: renderQueue, people: renderPeople, root: renderRoot, detail: renderDetail, agent: renderAgent };
function switchPage(p) {
  S.page = p;
  document.querySelectorAll('.page').forEach(s => s.classList.toggle('on', s.id === 'p-' + p));
  document.querySelectorAll('#tabs div').forEach(t => t.classList.toggle('on', t.dataset.p === p));
  $('pageTitle').textContent = TITLES[p];
  document.querySelector('.slicers').style.visibility = (p === 'detail' || p === 'agent') ? 'hidden' : 'visible';
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
