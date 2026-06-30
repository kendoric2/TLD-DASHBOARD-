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

// Local YYYY-MM-DD for "today" (used to skip auto-refresh on a finished custom range).
function todayISO(){ const d = new Date(); return new Date(d - d.getTimezoneOffset()*60000).toISOString().slice(0,10); }

// The current selection: a preset key, or a custom range with explicit From/To dates.
// `token` uniquely identifies the selection so refresh + stale checks work for custom too.
function currentSel(){
  const key = $("#range").value;
  if (key === "custom"){
    const s = $("#startDate").value, e = $("#endDate").value;
    return { key, start: s, end: e, token: `custom:${s}:${e}` };
  }
  return { key, start: null, end: null, token: key };
}
function qsFor(sel){
  return sel.key === "custom"
    ? `range=custom&start=${encodeURIComponent(sel.start)}&end=${encodeURIComponent(sel.end)}`
    : `range=${encodeURIComponent(sel.key)}`;
}
function showErr(msg){ const b = $("#errbar"); b.hidden = false; b.textContent = msg; }
function hideErr(){ $("#errbar").hidden = true; }
function validCustom(sel){
  if (!sel.start || !sel.end){ showErr("Pick both a start and end date."); return false; }
  if (sel.end < sel.start){ showErr("End date can’t be before the start date."); return false; }
  if ((new Date(sel.end) - new Date(sel.start)) / 86400000 > 366){ showErr("Custom range can’t exceed 12 months."); return false; }
  return true;
}

async function load() {
  const sel = currentSel();
  if (sel.key === "custom" && !validCustom(sel)){ $("#footer").textContent = "Pick a valid date range, then Apply."; return; }
  // On a same-range refresh, keep the last-known COST/CPA so the columns don't blink
  // to "…" every 30s — phase 2 refreshes them from the (warm) cache right after.
  const sameRange = lastData && lastData._range === sel.token;
  const prevCPA = {};
  if (sameRange) (lastData.agents || []).forEach(a => {
    if (a.cost !== undefined) prevCPA[a.name] = {cost: a.cost, cpa: a.cpa};
  });
  $("#footer").textContent = "Loading…";
  try {
    const res = await fetch(`/api/dashboard?${qsFor(sel)}`);
    const data = await res.json();
    if (data.error && !data.kpis){ showErr(data.error); $("#footer").textContent = "—"; return; }
    data._range = sel.token;
    if (sameRange) {                  // carry forward CPA so a refresh doesn't flicker
      (data.agents || []).forEach(a => { const p = prevCPA[a.name]; if (p) { a.cost = p.cost; a.cpa = p.cpa; } });
      if (lastData.kpis) { data.kpis.total_spend = lastData.kpis.total_spend; data.kpis.blended_cpa = lastData.kpis.blended_cpa; }
      if (lastData.agent_totals) data.agent_totals = lastData.agent_totals;
    }
    lastData = data;
    render(data);
    if (!data.demo) loadCPA(sel);   // phase 2: fill/refresh COST/CPA + cost tiles without blocking paint
  } catch (e) {
    $("#errbar").hidden = false;
    $("#errbar").textContent = "Could not reach the backend: " + e;
    $("#footer").textContent = "Offline.";
  } finally {
    armAuto(sel);   // (re)start the 30s countdown if Auto is ticked (skipped for finished custom ranges)
  }
}

/* Auto-refresh: while the box is ticked, reload every 30s. Re-arming on each
   load means the gap is always 30s since the last refresh (manual or auto). */
function armAuto(sel) {
  sel = sel || currentSel();
  clearInterval(autoTimer);
  autoTimer = null;
  if (!$("#autoRefresh").checked) return;
  // a finished (past) custom range can't change — don't poll it
  if (sel.key === "custom" && sel.end && sel.end < todayISO()) return;
  autoTimer = setInterval(load, AUTO_MS);
}

/* Phase 2: the heavy CPA report (COST, CPA, Total Spend, Blended CPA) loads on its
   own so it never blocks first paint. Those fields show "…" until this returns —
   which is instant once the server-side cache is warm. */
async function loadCPA(sel) {
  try {
    const res = await fetch(`/api/agent_cpa?${qsFor(sel)}`);
    const cpa = await res.json();
    if (!lastData || sel.token !== currentSel().token) return;   // ignore stale result after a change
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

// Policies by Carrier — pie chart in each carrier's brand color. Hovering a slice shows
// that carrier's policy count and its share of the total.
function renderCarrierChart(id, rows) {
  rows = rows || [];
  charts[id]?.destroy();
  const total = rows.reduce((s, r) => s + (r.count || 0), 0);
  charts[id] = new Chart(document.getElementById(id), {
    type: "pie",
    data: {
      labels: rows.map(r => r.label),
      datasets: [{
        data: rows.map(r => r.count),
        backgroundColor: rows.map((r, i) => carrierColor(r.label, i)),
        borderColor: "#fff",
        borderWidth: 2,
        hoverOffset: 8,                                  // hovered slice pops out slightly
      }],
    },
    options: {
      maintainAspectRatio: false,
      layout: { padding: 6 },
      plugins: {
        legend: { position: "right", labels: { boxWidth: 12, padding: 10, font: { size: 12 } } },
        tooltip: {
          callbacks: {
            // e.g. "Humana"  ->  " 17,570 policies · 38.3% of 45,840"
            label(ctx) {
              const v = ctx.parsed || 0;
              const pct = total ? (v / total * 100).toFixed(1) : "0.0";
              return ` ${v.toLocaleString()} policies · ${pct}% of ${total.toLocaleString()}`;
            },
          },
        },
      },
    },
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
  // commission is always set before submission, so a blank means "not in this pull" → em dash
  const money = v => (v === null || v === undefined || v === "")
    ? '<span class="dash">—</span>'
    : '$' + Number(v).toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2});
  $("#recent").innerHTML = (rows || []).map(r => {
    const date = r.date_sold ? String(r.date_sold).split(" ")[0] : "";
    const enroller = r.enroller ? r.enroller : '<span class="dash">—</span>';
    return `
    <tr>
      <td>${date}</td>
      <td>${r.agent ?? ""}</td><td class="num col-sep">${money(r.agent_commission)}</td>
      <td>${enroller}</td><td class="num col-sep">${money(r.fronter_commission)}</td>
      <td>${r.carrier ?? ""}</td>
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
function onRangeChange(){
  const isCustom = $("#range").value === "custom";
  $("#customRange").hidden = !isCustom;
  if (isCustom){
    if (!$("#startDate").value) $("#startDate").value = todayISO();
    if (!$("#endDate").value) $("#endDate").value = todayISO();
    hideErr();
    $("#footer").textContent = "Pick a date range, then Apply.";
  } else {
    hideErr();
    load();                                  // presets load immediately
  }
}
$("#range").addEventListener("change", onRangeChange);
$("#applyRange").addEventListener("click", load);
["startDate","endDate"].forEach(id => $("#"+id).addEventListener("keydown", e => { if (e.key === "Enter") load(); }));
$("#refresh").addEventListener("click", load);
$("#autoRefresh").addEventListener("change", () => armAuto());
document.querySelectorAll("th[data-sort]").forEach(th => {
  th.addEventListener("click", () => {
    const k = th.getAttribute("data-sort");
    if (sortKey === k) sortDir *= -1;
    else { sortKey = k; sortDir = (k === "name") ? 1 : -1; }
    if (lastData) renderAgents(lastData.agents);
  });
});

load();
