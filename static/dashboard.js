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
  }
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
  const cards = [
    {label:"Policies Sold",           value: fmt(k.policies_sold)},
    {label:"Billable Leads · Falcon", value: fmt(k.billable_leads)},
    {label:"Conversion Rate",         value: (k.conversion_rate ?? 0) + "%",
       note:"Falcon leads ending Active or Sale"},
    {label:"Avg Premium · GTL only",  value: "$" + fmt(k.avg_gtl_premium),
       note:"GTL is the only carrier with premium"},
  ];
  $("#kpis").innerHTML = cards.map(c => `
    <div class="kpi">
      <div class="label">${c.label}</div>
      <div class="value">${c.value}</div>
      <div class="delta note">${c.note || ""}</div>
    </div>`).join("");
}

function renderDoughnut(id, rows) {
  rows = rows || [];
  const colors = [C('--brand'),C('--brand-2'),C('--good'),C('--warn'),'#8E7CC3','#B7C2D0','#9FB3C8'];
  charts[id]?.destroy();
  charts[id] = new Chart(document.getElementById(id), {
    type:'doughnut',
    data:{labels: rows.map(r=>r.label),
      datasets:[{data: rows.map(r=>r.count),
        backgroundColor: rows.map((_,i)=>colors[i%colors.length]), borderWidth:0}]},
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
    const prem = Number(r.premium) > 0
      ? '$' + Number(r.premium).toLocaleString()
      : '<span class="dash">—</span>';
    return `
    <tr>
      <td>${date}</td><td>${r.agent ?? ""}</td>
      <td>${r.product ?? ""}</td><td>${r.carrier ?? ""}</td>
      <td class="num">${prem}</td>
      <td><span class="pill ${String(r.status||'').toLowerCase()}">${r.status ?? ""}</span></td>
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
      <td class="num">${(a.leads||0).toLocaleString()}</td>
    </tr>`).join("");
}

/* ---- GUI events ---- */
$("#range").addEventListener("change", load);
$("#refresh").addEventListener("click", load);
document.querySelectorAll("th[data-sort]").forEach(th => {
  th.addEventListener("click", () => {
    const k = th.getAttribute("data-sort");
    if (sortKey === k) sortDir *= -1;
    else { sortKey = k; sortDir = (k === "name") ? 1 : -1; }
    if (lastData) renderAgents(lastData.agents);
  });
});

load();
