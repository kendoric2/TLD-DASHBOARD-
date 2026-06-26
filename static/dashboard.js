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
  $("#footer").textContent = "Loading…";
  try {
    const res = await fetch(`/api/dashboard?range=${encodeURIComponent(range)}`);
    const data = await res.json();
    lastData = data;
    render(data);
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

function render(d) {
  $("#demoBadge").hidden = !d.demo;
  if (d.error) { $("#errbar").hidden = false; $("#errbar").textContent = d.error; }
  else { $("#errbar").hidden = true; }

  document.querySelectorAll(".rangeLabel").forEach(e => e.textContent = d.range_label);

  renderKPIs(d.kpis);
  renderDoughnut("carrier", d.by_carrier);
  renderBar("product", d.by_plan);
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
  const cards = [
    {label:"Policies Sold",     value: fmt(k.policies_sold)},
    {label:"Billable Leads",    value: fmt(k.billable_leads),
       note:"All vendors · billable"},
    {label:"Conversion Rate",   value: (k.conversion_rate ?? 0) + "%",
       note:"Billable leads ending Active or Sale"},
    {label:"Total Spend",       value: money0(k.total_spend),
       note:"Lead cost this period"},
    {label:"Blended CPA",       value: "$" + Number(k.blended_cpa ?? 0).toFixed(2),
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

function renderDoughnut(id, rows) {
  rows = rows || [];
  charts[id]?.destroy();
  charts[id] = new Chart(document.getElementById(id), {
    type:'doughnut',
    data:{labels: rows.map(r=>r.label),
      datasets:[{data: rows.map(r=>r.count),
        backgroundColor: rows.map((r,i)=>carrierColor(r.label,i)), borderWidth:0}]},
    options:{cutout:'62%', plugins:{legend:{position:'right', labels:{boxWidth:12, font:{size:12}}}},
      maintainAspectRatio:false}
  });
}

function renderBar(id, rows) {
  rows = rows || [];
  charts[id]?.destroy();
  charts[id] = new Chart(document.getElementById(id), {
    type:'bar',
    data:{labels: rows.map(r=>r.label),
      datasets:[{data: rows.map(r=>r.count), backgroundColor:C('--brand'), borderRadius:6, barThickness:46}]},
    options:{indexAxis:'y', plugins:{legend:{display:false}},
      scales:{x:{grid:{color:C('--line')}}, y:{grid:{display:false}}}, maintainAspectRatio:false}
  });
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
  $("#agents").innerHTML = sorted.map((a,i) => `
    <tr>
      <td><span class="rank ${i===0?'top':''}">${i+1}</span>${a.name}</td>
      <td><div class="bar-cell"><div class="bar-track"><div class="bar-fill" style="width:${((a.policies||0)/maxP*100).toFixed(0)}%"></div></div><span>${(a.policies||0).toLocaleString()}</span></div></td>
      <td class="num">${a.cost != null ? '$' + Number(a.cost).toLocaleString(undefined,{maximumFractionDigits:0}) : '—'}</td>
      <td class="num">${a.cpa != null ? '$' + Number(a.cpa).toFixed(2) : '—'}</td>
    </tr>`).join("");

  // agent count next to the section title
  $("#agentCount").textContent = rows.length ? ` · ${rows.length} agents` : "";

  // pinned totals row (totals come from the report; policies summed from the table)
  const t = lastData && lastData.agent_totals;
  $("#agentTotals").innerHTML = t ? `
    <tr>
      <td>Totals</td>
      <td class="num">${Number(t.policies||0).toLocaleString()}</td>
      <td class="num">$${Number(t.cost||0).toLocaleString(undefined,{maximumFractionDigits:0})}</td>
      <td class="num">$${Number(t.cpa||0).toFixed(2)}</td>
    </tr>` : "";
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
