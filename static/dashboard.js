/* ============================================================
   GUI LAYER
   Fetches JSON from the Python backend (/api/dashboard) and renders it.
   No API keys, no TLDCRM calls here — that all lives in Python.
   ============================================================ */
const $ = s => document.querySelector(s);
const C = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();

let charts = {};          // keep chart instances so we can destroy before redraw
let lastData = null;      // cache for client-side sorting
let sortKey = "policies", sortDir = -1;
let autoTimer = null;     // handle for the auto-refresh interval
const AUTO_MS = 30000;    // auto-refresh every 30 seconds

async function load() {
  const range = $("#range").value;
  // On a same-range refresh, keep the last-known COST/CPA so the columns don't blink
  // to "…" every 30s — phase 2 refreshes them from the (warm) cache right after.
  const sameRange = lastData && lastData._range === range;
  const prevCPA = {};
  if (sameRange) (lastData.agents || []).forEach(a => {
    if (a.cost !== undefined) prevCPA[a.name] = {cost: a.cost, cpa: a.cpa};
  });
  $("#footer").textContent = "Loading…";
  try {
    const res = await fetch(`/api/dashboard?range=${encodeURIComponent(range)}`);
    const data = await res.json();
    data._range = range;
    if (sameRange) {                  // carry forward CPA so a refresh doesn't flicker
      (data.agents || []).forEach(a => { const p = prevCPA[a.name]; if (p) { a.cost = p.cost; a.cpa = p.cpa; } });
      if (lastData.kpis) { data.kpis.total_spend = lastData.kpis.total_spend; data.kpis.blended_cpa = lastData.kpis.blended_cpa; }
      if (lastData.agent_totals) data.agent_totals = lastData.agent_totals;
    }
    lastData = data;
    render(data);
    if (!data.demo) loadCPA(range);   // phase 2: fill/refresh COST/CPA + cost tiles without blocking paint
  } catch (e) {
    $("#errbar").hidden = false;
    $("#errbar").textContent = "Could not reach the backend: " + e;
    $("#footer").textContent = "Offline.";
  } finally {
    armAuto();   // (re)start the 30s countdown if Auto is ticked
  }
}

/* Auto-refresh: while the box is ticked, reload every 30s. Re-arming on each
   load means the gap is always 30s since the last refresh (manual or auto). */
function armAuto() {
  clearInterval(autoTimer);
  autoTimer = null;
  if ($("#autoRefresh").checked) autoTimer = setInterval(load, AUTO_MS);
}

/* Phase 2: the heavy CPA report (COST, CPA, Total Spend, Blended CPA) loads on its
   own so it never blocks first paint. Those fields show "…" until this returns —
   which is instant once the server-side cache is warm. */
async function loadCPA(range) {
  try {
    const res = await fetch(`/api/agent_cpa?range=${encodeURIComponent(range)}`);
    const cpa = await res.json();
    if (!lastData || range !== $("#range").value) return;   // ignore stale result after a range switch
    applyCPA(cpa);
  } catch (e) { /* leave the "…" placeholders — not fatal */ }
}

function applyCPA(cpa) {
  const map = (cpa && cpa.by_agent) || {};
  (lastData.agents || []).forEach(a => {
    const [full, loose] = nameKeys(a.name);
    const rec = map[full] || map[loose] || null;
    a.cost = rec ? rec.cost : null;          // null => "—" (no match); undefined only before this runs
    a.cpa  = rec ? rec.cpa  : null;
  });
  const tot = (cpa && cpa.totals) || {};
  lastData.kpis = lastData.kpis || {};
  lastData.kpis.total_spend = tot.cost ?? 0;
  lastData.kpis.blended_cpa = tot.cpa ?? 0;
  lastData.kpis.billable_calls = tot.billable_calls ?? 0;
  lastData.kpis.conversion_rate = tot.conversion ?? 0;
  lastData.agent_totals = {
    policies: (lastData.agents || []).reduce((s, a) => s + (a.policies || 0), 0),
    cost: tot.cost ?? 0,
    cpa: tot.cpa ?? 0,
  };
  renderKPIs(lastData.kpis);
  renderAgents(lastData.agents);
}

/* Mirror of tldcrm_client._name_keys so agent rows match the CPA report's names
   ("Last, First" <-> "First Last", plus a loose first+last key for middle names). */
function nameKeys(s) {
  s = (s || "").trim().toLowerCase();
  const i = s.indexOf(",");
  if (i >= 0) s = (s.slice(i + 1).trim() + " " + s.slice(0, i).trim()).trim();
  const toks = s.split(/\s+/).filter(Boolean);
  const full = toks.join(" ");
  const loose = toks.length >= 2 ? `${toks[0]} ${toks[toks.length - 1]}` : full;
  return [full, loose];
}

function render(d) {
  $("#demoBadge").hidden = !d.demo;
  if (d.error) { $("#errbar").hidden = false; $("#errbar").textContent = d.error; }
  else { $("#errbar").hidden = true; }

  document.querySelectorAll(".rangeLabel").forEach(e => e.textContent = d.range_label);

  renderKPIs(d.kpis);
  renderCarrierChart("carrier", d.by_carrier);
  renderEnrollments(d.enrollments);
  renderRecent(d.recent_sales);
  renderAgents(d.agents);

  $("#updated").textContent = new Date().toLocaleString();
  const dr = d.date_range ? ` · ${d.date_range.start} → ${d.date_range.end}` : "";
  $("#footer").textContent = (d.demo
    ? "Showing sample data — add your TLDCRM API key to .env to go live."
    : "Live, read-only data pulled from TLDCRM.") + dr;
}

function renderKPIs(k) {
  const fmt = n => (n ?? 0).toLocaleString();
  const money0 = n => "$" + Number(n ?? 0).toLocaleString(undefined, {maximumFractionDigits:0});
  const wait = (v, fn) => v === undefined ? '<span class="dash">…</span>' : fn(v);   // "…" until phase 2
  const cards = [
    {label:"Policies Sold",     value: fmt(k.policies_sold)},
    {label:"Billable Calls",    value: wait(k.billable_calls, fmt),
       note:"Billable dial/transfer calls"},
    {label:"Conversion Rate",   value: wait(k.conversion_rate, v => v + "%"),
       note:"Falcon sales ÷ billable calls"},
    {label:"Total Spend",       value: wait(k.total_spend, money0),
       note:"Lead cost this period"},
    {label:"Blended CPA",       value: wait(k.blended_cpa, v => "$" + Number(v).toFixed(2)),
       note:"Total spend ÷ sales"},
    {label:"Avg Premium · GTL", value: money0(k.avg_gtl_premium),
       note:"GTL is the only carrier with premium"},
  ];
  $("#kpis").innerHTML = cards.map(c => `
    <div class="kpi">
      <div class="label">${c.label}</div>
      <div class="value">${c.value}</div>
      <div class="delta note">${c.note || ""}</div>
    </div>`).join("");
}

// Carrier brand colors (from each carrier's logo/website). Matched by name;
// unknown carriers fall back to a neutral slate palette.
const CARRIER_COLORS = {
  aetna:"#7D3F98",
  unitedhealthcare:"#002677", uhc:"#002677",
  humana:"#5BA908",
  cigna:"#0080C9",
  wellcare:"#009CA6",
  guaranteetrustlife:"#07436F", gtl:"#07436F",
  anthem:"#0077C6", elevance:"#0077C6",
  bluecross:"#0099CC", bcbs:"#0099CC",
  kaiserpermanente:"#006BA7", kaiser:"#006BA7",
  mutualofomaha:"#003A70",
};
const CARRIER_FALLBACK = ['#7E8AA8','#A9B7C9','#5B6B86','#C0CAD8','#8E9BB0','#6B7C93'];
function carrierColor(label, i) {
  const k = String(label || "").toLowerCase().replace(/[^a-z0-9]/g, "");
  for (const key in CARRIER_COLORS) { if (k.includes(key)) return CARRIER_COLORS[key]; }
  return CARRIER_FALLBACK[i % CARRIER_FALLBACK.length];
}

// Draws the value on top of each vertical bar (small custom plugin — no extra CDN).
const barTopLabels = {
  id: "barTopLabels",
  afterDatasetsDraw(chart) {
    const ctx = chart.ctx;
    const meta = chart.getDatasetMeta(0);
    if (!meta || !meta.data) return;
    ctx.save();
    ctx.fillStyle = C("--brand-dark");
    ctx.font = '700 13px -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif';
    ctx.textAlign = "center";
    ctx.textBaseline = "bottom";
    meta.data.forEach((bar, i) => {
      const v = chart.data.datasets[0].data[i];
      if (v != null) ctx.fillText(Number(v).toLocaleString(), bar.x, bar.y - 4);
    });
    ctx.restore();
  }
};

// Policies by Carrier — vertical bars in each carrier's brand color, total on top.
function renderCarrierChart(id, rows) {
  rows = rows || [];
  charts[id]?.destroy();
  charts[id] = new Chart(document.getElementById(id), {
    type: "bar",
    data: { labels: rows.map(r => r.label),
      datasets: [{ data: rows.map(r => r.count),
        backgroundColor: rows.map((r, i) => carrierColor(r.label, i)),
        borderRadius: 6, maxBarThickness: 70 }] },
    options: {
      layout: { padding: { top: 24 } },                 // headroom for the top labels
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { display: false } },
        y: { beginAtZero: true, grid: { color: C("--line") }, ticks: { precision: 0 } }
      },
      maintainAspectRatio: false
    },
    plugins: [barTopLabels]
  });
}

function renderEnrollments(e) {
  e = e || {total: 0, by_enroller: []};
  $("#enrollTotal").textContent = (e.total || 0).toLocaleString();
  const list = e.by_enroller || [];
  $("#enrollList").innerHTML = list.length
    ? list.map(g => `
      <div class="enroll-row"><span class="enroll-name">${g.name ?? g.fronter_id}</span><span class="enroll-count">${(g.count || 0).toLocaleString()}</span></div>`).join("")
    : '<div class="dash" style="padding:10px 2px">No enrollments yet</div>';
}

function renderRecent(rows) {
  $("#recent").innerHTML = (rows || []).map(r => {
    const date = r.date_sold ? String(r.date_sold).split(" ")[0] : "";
    const enroller = r.enroller ? r.enroller : '<span class="dash">—</span>';
    return `
    <tr>
      <td>${date}</td><td>${r.agent ?? ""}</td>
      <td>${enroller}</td><td>${r.carrier ?? ""}</td>
    </tr>`;
  }).join("");
}

function renderAgents(rows) {
  rows = rows || [];
  const sorted = [...rows].sort((a,b) => {
    let x = a[sortKey], y = b[sortKey];
    if (typeof x === "string" || typeof y === "string")
      return sortDir * String(x ?? "").localeCompare(String(y ?? ""));
    return sortDir * ((x || 0) - (y || 0));
  });
  const maxP = Math.max(1, ...rows.map(a => a.policies || 0));
  // COST/CPA show "…" until phase 2 loads them (undefined), "—" if no match (null).
  const money0 = v => '$' + Number(v).toLocaleString(undefined,{maximumFractionDigits:0});
  const wait = (v, fn) => v === undefined ? '…' : (v === null ? '—' : fn(v));
  $("#agents").innerHTML = sorted.map((a,i) => `
    <tr>
      <td><span class="rank ${i===0?'top':''}">${i+1}</span>${a.name}</td>
      <td><div class="bar-cell"><div class="bar-track"><div class="bar-fill" style="width:${((a.policies||0)/maxP*100).toFixed(0)}%"></div></div><span>${(a.policies||0).toLocaleString()}</span></div></td>
      <td class="num">${wait(a.cost, money0)}</td>
      <td class="num">${wait(a.cpa, v => '$' + Number(v).toFixed(2))}</td>
    </tr>`).join("");

  // agent count next to the section title
  $("#agentCount").textContent = rows.length ? ` · ${rows.length} agents` : "";

  // pinned totals row: policies sum is known immediately; cost/CPA fill in with phase 2.
  const totPolicies = rows.reduce((s, a) => s + (a.policies || 0), 0);
  const t = lastData && lastData.agent_totals;
  $("#agentTotals").innerHTML = `
    <tr>
      <td>Totals</td>
      <td class="num">${totPolicies.toLocaleString()}</td>
      <td class="num">${t ? money0(t.cost || 0) : '…'}</td>
      <td class="num">${t ? '$' + Number(t.cpa || 0).toFixed(2) : '…'}</td>
    </tr>`;
}

/* ---- GUI events ---- */
$("#range").addEventListener("change", load);
$("#refresh").addEventListener("click", load);
$("#autoRefresh").addEventListener("change", armAuto);
document.querySelectorAll("th[data-sort]").forEach(th => {
  th.addEventListener("click", () => {
    const k = th.getAttribute("data-sort");
    if (sortKey === k) sortDir *= -1;
    else { sortKey = k; sortDir = (k === "name") ? 1 : -1; }
    if (lastData) renderAgents(lastData.agents);
  });
});

load();
