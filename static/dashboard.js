/* ============================================================
   GUI LAYER
   Fetches JSON from the Python backend (/api/dashboard) and renders it.
   No API keys, no TLDCRM calls here — that all lives in Python.
   ============================================================ */
const $ = s => document.querySelector(s);
const C = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();

// Money with thousands separators + 2 decimals — e.g. 1787 -> "$1,787.00".
// (toFixed() alone gives "$1787.00", which is why CPA used to lose its commas.)
const money2 = v => "$" + Number(v || 0).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});

let charts = {};          // keep chart instances so we can destroy before redraw
let selectedCarrier = null;  // carrier slice currently shown in the detail panel
let selectedState = null;    // state currently shown in the map's detail panel
let stateByAbbr = {};        // state abbr -> its breakdown, for click-through
let selectedActiveCarrier = null;  // carrier row selected in the Active Policies tile
let activeByCarrier = {};          // carrier -> its active breakdown (incl states)
let activeCombined = null;         // aggregate active-by-state across all carriers (default view)
let lastRecentRows = [];           // Sales rows, kept so sorting never refetches
let recentSortKey = "date_sold", recentSortDir = -1;   // newest sale first by default
let lastBilledRows = [];           // Invoice-audit rows, kept so sorting never refetches
let billedSortKey = "call_date", billedSortDir = -1;   // newest call first by default
let lastDetailRows = [];           // Agent Detail rows, kept so sorting never refetches
let detailSortKey = "date_sold", detailSortDir = -1;   // newest first by default
let selectedEnroller = null;       // enroller row selected in the Enrollments tile
let enrollById = {};               // fronter_id -> enroller (incl detail)
let boardOpen = true;     // sales board expanded (true) or collapsed to its tab (false)
let boardAuto = true;     // board auto-anchors to this-week-to-date until the user picks a custom range
let lastBoard = null;     // last sales-board payload, so re-sorting never refetches
let boardSortKey = "total", boardSortDir = -1;   // board sort: -1 = high→low (numbers), 1 = A→Z (name)
let lastData = null;      // cache for client-side sorting
let sortKey = "policies", sortDir = -1;
let autoTimer = null;     // handle for the auto-refresh interval
const AUTO_MS = 30000;    // auto-refresh every 30 seconds

// Local YYYY-MM-DD for "today" (used to skip auto-refresh on a finished custom range).
function todayISO(){ const d = new Date(); return new Date(d - d.getTimezoneOffset()*60000).toISOString().slice(0,10); }

/* ===== Custom From/To date pickers: flatpickr calendar + a relative-times menu ===== */
let fpStart = null, fpEnd = null;
const fpById = {};        // field id -> its flatpickr instance (main picker + board picker)

function mkdate(y, mo, d){
  const dt = new Date(y, mo - 1, d);
  return (dt.getFullYear() === y && dt.getMonth() === mo - 1 && dt.getDate() === d) ? dt : null;
}
// Accept M/D/YYYY, M/D/YY, or YYYY-MM-DD when typed; returns a Date or null.
function parseDateInput(s){
  s = (s || "").trim();
  let m = s.match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/);  if (m) return mkdate(+m[1], +m[2], +m[3]);
  m = s.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);     if (m) return mkdate(+m[3], +m[1], +m[2]);
  m = s.match(/^(\d{1,2})\/(\d{1,2})\/(\d{2})$/);     if (m) return mkdate(2000 + +m[3], +m[1], +m[2]);
  return null;
}
function toISO(dt){ return `${dt.getFullYear()}-${String(dt.getMonth()+1).padStart(2,"0")}-${String(dt.getDate()).padStart(2,"0")}`; }
function pickerISO(id){ const dt = parseDateInput($("#"+id).value); return dt ? toISO(dt) : ""; }
function setPicker(fp, id, dt){
  if (fp) fp.setDate(dt, true);   // keeps flatpickr + the input text in sync
  else { const p = n => String(n).padStart(2,"0"); $("#"+id).value = `${p(dt.getMonth()+1)}/${p(dt.getDate())}/${dt.getFullYear()}`; }
}

function initDatePickers(){
  const opts = { dateFormat: "m/d/Y", allowInput: true, disableMobile: true };
  const mk = id => (typeof flatpickr !== "undefined" && $("#"+id)) ? flatpickr("#"+id, opts) : null;
  fpStart = mk("startDate"); fpEnd = mk("endDate");          // clicking a field opens the calendar grid
  fpById["startDate"] = fpStart; fpById["endDate"] = fpEnd;
  fpById["boardStart"] = mk("boardStart"); fpById["boardEnd"] = mk("boardEnd");
  fpById["detailStart"] = mk("detailStart"); fpById["detailEnd"] = mk("detailEnd");
  fpById["vendorStart"] = mk("vendorStart"); fpById["vendorEnd"] = mk("vendorEnd");
  [["startMenuBtn","startDate"], ["endMenuBtn","endDate"],
   ["boardStartMenuBtn","boardStart"], ["boardEndMenuBtn","boardEnd"],
   ["detailStartMenuBtn","detailStart"], ["detailEndMenuBtn","detailEnd"],
   ["vendorStartMenuBtn","vendorStart"], ["vendorEndMenuBtn","vendorEnd"]].forEach(([btn, fld]) => {
    const el = $("#"+btn);
    if (el) el.addEventListener("click", (e) => { e.stopPropagation(); openRelMenu(fld, e.currentTarget); });
  });
  document.addEventListener("click", (e) => { if (relMenu && !relMenu.contains(e.target)) closeRelMenu(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeRelMenu(); });
}

/* --- relative-times menu (the calendar-icon popup) --- */
let relMenu = null, relTarget = null;
const WK = ["Sunday","Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"];
function startOfWeek(base){ const x = new Date(base); x.setHours(0,0,0,0); x.setDate(x.getDate() - x.getDay()); return x; }  // Sunday
function startOfQuarter(base){ return new Date(base.getFullYear(), Math.floor(base.getMonth()/3)*3, 1); }

function resolveRel(rel){
  const t = new Date(); t.setHours(0,0,0,0);
  if (rel === "today") return t;
  if (rel === "yesterday"){ const d = new Date(t); d.setDate(d.getDate()-1); return d; }
  if (rel === "this-week") return startOfWeek(t);
  if (rel === "this-month") return new Date(t.getFullYear(), t.getMonth(), 1);
  if (rel === "this-quarter") return startOfQuarter(t);
  if (rel === "this-year") return new Date(t.getFullYear(), 0, 1);
  if (rel === "last-week"){ const s = startOfWeek(t); s.setDate(s.getDate()-7); return s; }
  if (rel === "last-month") return new Date(t.getFullYear(), t.getMonth()-1, 1);
  if (rel === "last-quarter"){ const s = startOfQuarter(t); s.setMonth(s.getMonth()-3); return s; }
  if (rel === "last-year") return new Date(t.getFullYear()-1, 0, 1);
  if (rel.startsWith("this-dow-")){ const s = startOfWeek(t); s.setDate(s.getDate() + (+rel.slice(9))); return s; }
  if (rel.startsWith("last-dow-")){ const s = startOfWeek(t); s.setDate(s.getDate() - 7 + (+rel.slice(9))); return s; }
  return null;
}
function resolveAgo(num, unit){
  const d = new Date(); d.setHours(0,0,0,0);
  num = Math.max(1, parseInt(num, 10) || 1);
  if (unit === "days") d.setDate(d.getDate() - num);
  else if (unit === "weeks") d.setDate(d.getDate() - 7*num);
  else if (unit === "months") d.setMonth(d.getMonth() - num);
  return d;
}
function relMenuHTML(){
  const dows = pfx => WK.map((d,i) => `<button type="button" data-rel="${pfx}-dow-${i}">${d}</button>`).join("");
  return `
    <div class="relmenu-head"><span>Relative Times</span><button type="button" class="relmenu-x" data-close="1">&times;</button></div>
    <div class="relrow"><button type="button" data-rel="today">Today</button><button type="button" data-rel="yesterday">Yesterday</button></div>
    <div class="relrow"><input type="number" class="relnum" value="1" min="1" />
      <button type="button" class="unit" data-unit="days">Days</button>
      <button type="button" class="unit" data-unit="weeks">Weeks</button>
      <button type="button" class="unit active" data-unit="months">Months</button>
      <span class="relago">Ago</span></div>
    <div class="relmenu-h">Beginning of This</div>
    <div class="relrow"><button type="button" data-rel="this-week">Week</button><button type="button" data-rel="this-month">Month</button><button type="button" data-rel="this-quarter">Quarter</button><button type="button" data-rel="this-year">Year</button></div>
    <div class="relrow">${dows("this")}</div>
    <div class="relmenu-h">Beginning of Last</div>
    <div class="relrow"><button type="button" data-rel="last-week">Week</button><button type="button" data-rel="last-month">Month</button><button type="button" data-rel="last-quarter">Quarter</button><button type="button" data-rel="last-year">Year</button></div>
    <div class="relrow">${dows("last")}</div>`;
}
function openRelMenu(targetId, anchor){
  closeRelMenu();
  relTarget = targetId;
  relMenu = document.createElement("div");
  relMenu.className = "relmenu";
  relMenu.innerHTML = relMenuHTML();
  document.body.appendChild(relMenu);
  const r = anchor.getBoundingClientRect();
  relMenu.style.top = `${r.bottom + 6}px`;
  relMenu.style.left = `${Math.max(8, Math.min(r.left, window.innerWidth - relMenu.offsetWidth - 10))}px`;
  relMenu.addEventListener("click", onRelMenuClick);
}
function closeRelMenu(){ if (relMenu){ relMenu.remove(); relMenu = null; relTarget = null; } }
function applyRelDate(dt){
  setPicker(fpById[relTarget], relTarget, dt);
  if (relTarget === "boardStart" || relTarget === "boardEnd") boardAuto = false;  // user took control of the board range
  hideErr();
  closeRelMenu();
}
function onRelMenuClick(e){
  const b = e.target.closest("button");
  if (!b) return;
  e.stopPropagation();
  if (b.dataset.close){ closeRelMenu(); return; }
  if (b.dataset.rel){ const dt = resolveRel(b.dataset.rel); if (dt) applyRelDate(dt); return; }
  if (b.dataset.unit){ applyRelDate(resolveAgo(relMenu.querySelector(".relnum").value, b.dataset.unit)); }
}

// The selection is always the From/To date range now (the preset dropdown was removed —
// the relative-times menu covers presets). `token` identifies the range so refresh + stale
// checks keep working.
function currentSel(){
  const s = pickerISO("startDate"), e = pickerISO("endDate");
  return { key: "custom", start: s, end: e, token: `custom:${s}:${e}` };
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

// force=true (the Refresh button / Apply) skips the server's short-lived memory copy of the
// heavy CPA report and pulls everything straight from TLD. Auto-refresh calls load() plain.
async function load(force) {
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
  // Fire all three requests AT ONCE — none of them depends on the others. The CPA report is
  // the slow one (~30s on a big month), so starting it now instead of after the dashboard
  // comes back takes that time off the total wait.
  const dashReq = fetch(`/api/dashboard?${qsFor(sel)}`);
  const cpaReq = fetchCPA(sel, force);
  if (boardOpen) boardLoad();
  try {
    const res = await dashReq;
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
    // The CPA request is already in flight; apply it whenever it lands (it may already
    // have). Ignored if the user moved to another range in the meantime.
    if (!data.demo) cpaReq.then(cpa => {
      if (cpa && lastData && sel.token === currentSel().token) applyCPA(cpa);
    });
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
  autoTimer = setInterval(() => load(), AUTO_MS);   // auto-refresh never forces
}

/* Phase 2: the heavy CPA report (COST, CPA, Total Spend, Blended CPA) loads on its
   own so it never blocks first paint. Those fields show "…" until this returns —
   which is instant once the server-side cache is warm. */
// Kick off the heavy CPA report and hand back a promise of its JSON. Started alongside the
// dashboard request (they're independent) and applied once the page data is in place.
function fetchCPA(sel, force) {
  return fetch(`/api/agent_cpa?${qsFor(sel)}${force ? "&force=1" : ""}`)
    .then(r => r.json())
    .catch(() => null);          // leave the "…" placeholders — not fatal
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
  renderActive(d.active_by_carrier);
  renderStates(d.by_state);
  renderRecent(d.recent_sales);
  renderAgents(d.agents);

  $("#updated").textContent = new Date().toLocaleString();
  const dr = d.date_range ? ` · ${d.date_range.start} → ${d.date_range.end}` : "";
  // A cached range is only served after TLD confirms nothing in it changed — but say so
  // anyway, so a cached number is never silently mistaken for a fresh one.
  const src = d.demo
    ? "Showing sample data — add your TLDCRM API key to .env to go live."
    : (d.cached_at
        ? `Saved copy from ${d.cached_at}, re-checked against TLDCRM just now — nothing changed.`
        : "Live, read-only data pulled from TLDCRM.");
  $("#footer").textContent = src + dr;
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
       note:"All vendors · sales ÷ billable calls"},
    {label:"Total Spend",       value: wait(k.total_spend, money0),
       note:"Lead cost this period"},
    {label:"Blended CPA",       value: wait(k.blended_cpa, money2),
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
      onHover(evt, els){ if (evt.native) evt.native.target.style.cursor = els.length ? "pointer" : "default"; },
      onClick(evt, els){
        if (!els.length) return;
        const i = els[0].index;
        selectedCarrier = rows[i].label;
        renderCarrierDetail(rows[i], i);
      },
      plugins: {
        legend: {
          position: "right",
          labels: {
            boxWidth: 12, padding: 10, font: { size: 12 },
            // show each carrier's deal count in the legend, e.g. "UHC - 10"
            generateLabels(chart){
              const ds = chart.data.datasets[0];
              return chart.data.labels.map((label, i) => ({
                text: `${label} - ${Number(ds.data[i] || 0).toLocaleString()}`,
                fillStyle: ds.backgroundColor[i],
                strokeStyle: ds.backgroundColor[i],
                lineWidth: 0,
                hidden: !chart.getDataVisibility(i),
                index: i,
              }));
            },
          },
        },
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
  // keep the selected carrier's detail visible across refreshes (numbers update); else prompt
  const idx = rows.findIndex(r => r.label === selectedCarrier);
  renderCarrierDetail(idx >= 0 ? rows[idx] : null, idx);
}

// Detail panel under the pie — Total Deals + how many were Enrolled (deals with a fronter).
function renderCarrierDetail(row, i){
  const el = $("#carrierDetail");
  if (!el) return;
  if (!row){ el.innerHTML = '<div class="cd-hint">Click a carrier for its details</div>'; return; }
  const total = row.count || 0, enr = row.enrolled || 0;
  const pct = total ? (enr / total * 100).toFixed(1) : "0.0";
  el.innerHTML = `
    <div class="cd-name"><span class="cd-dot" style="background:${carrierColor(row.label, i)}"></span>${row.label}</div>
    <div class="cd-stats">
      <div><div class="cd-v">${total.toLocaleString()}</div><div class="cd-l">Total Deals</div></div>
      <div><div class="cd-v">${enr.toLocaleString()}</div><div class="cd-l">Enrolled · ${pct}%</div></div>
    </div>`;
}

/* ===== Production by State: US choropleth (chartjs-chart-geo) + ranked-list fallback ===== */
let _usTopo = null, _geoRegistered = false;
const US_TOPO_URL = "https://cdn.jsdelivr.net/npm/us-atlas@3/states-10m.json";
const STATE_ABBR = {
  "Alabama":"AL","Alaska":"AK","Arizona":"AZ","Arkansas":"AR","California":"CA","Colorado":"CO",
  "Connecticut":"CT","Delaware":"DE","District of Columbia":"DC","Florida":"FL","Georgia":"GA",
  "Hawaii":"HI","Idaho":"ID","Illinois":"IL","Indiana":"IN","Iowa":"IA","Kansas":"KS","Kentucky":"KY",
  "Louisiana":"LA","Maine":"ME","Maryland":"MD","Massachusetts":"MA","Michigan":"MI","Minnesota":"MN",
  "Mississippi":"MS","Missouri":"MO","Montana":"MT","Nebraska":"NE","Nevada":"NV","New Hampshire":"NH",
  "New Jersey":"NJ","New Mexico":"NM","New York":"NY","North Carolina":"NC","North Dakota":"ND",
  "Ohio":"OH","Oklahoma":"OK","Oregon":"OR","Pennsylvania":"PA","Rhode Island":"RI","South Carolina":"SC",
  "South Dakota":"SD","Tennessee":"TN","Texas":"TX","Utah":"UT","Vermont":"VT","Virginia":"VA",
  "Washington":"WA","West Virginia":"WV","Wisconsin":"WI","Wyoming":"WY","Puerto Rico":"PR"
};
const STATE_NAME = Object.fromEntries(Object.entries(STATE_ABBR).map(([n, a]) => [a, n]));

function renderStateList(byState){
  const el = $("#stateList");
  if (!el) return;
  el.innerHTML = (byState && byState.length)
    ? byState.map(s => `<span class="st" data-state="${s.state}">${s.state} <b>${(s.count || 0).toLocaleString()}</b></span>`).join("")
    : '<span class="dash">No production in this range.</span>';
}
function showStateFallback(on){
  const wrap = document.querySelector(".state-wrap");
  if (wrap) wrap.style.display = on ? "none" : "";
  const list = $("#stateList");
  if (list) list.hidden = !on;
}
async function loadUSTopo(){
  if (_usTopo) return _usTopo;
  const us = await fetch(US_TOPO_URL).then(r => r.json());
  _usTopo = ChartGeo.topojson.feature(us, us.objects.states).features;
  return _usTopo;
}
async function renderStates(byState){
  byState = byState || [];
  renderStateList(byState);                         // keep the fallback list ready
  const counts = {};
  stateByAbbr = {};
  byState.forEach(s => { const a = String(s.state || "").toUpperCase(); counts[a] = s.count || 0; stateByAbbr[a] = s; });
  renderStateDetail(selectedState ? stateByAbbr[selectedState] : null);   // restore selection or prompt
  const canvas = $("#stateMap");
  if (typeof ChartGeo === "undefined" || !canvas){ showStateFallback(true); return; }
  try {
    if (!_geoRegistered){
      Chart.register(ChartGeo.ChoroplethController, ChartGeo.GeoFeature, ChartGeo.ColorScale, ChartGeo.ProjectionScale);
      _geoRegistered = true;
    }
    const feats = await loadUSTopo();
    const max = Math.max(1, ...Object.values(counts));
    charts.stateMap?.destroy();
    charts.stateMap = new Chart(canvas, {
      type: "choropleth",
      data: {
        labels: feats.map(f => f.properties.name),
        datasets: [{
          outline: feats,
          data: feats.map(f => ({ feature: f, value: counts[STATE_ABBR[f.properties.name]] || 0 })),
        }],
      },
      options: {
        maintainAspectRatio: false,
        showOutline: true,
        showGraticule: false,
        onHover(evt, els){ if (evt.native) evt.native.target.style.cursor = els.length ? "pointer" : "default"; },
        onClick(evt, els){
          if (!els.length) return;
          const abbr = STATE_ABBR[feats[els[0].index].properties.name];
          selectedState = abbr;
          renderStateDetail(stateByAbbr[abbr] || {state: abbr, count: 0, enrolled: 0, carriers: [], agents: []});
        },
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { label(ctx){
            const v = (ctx.raw && ctx.raw.value) || 0;
            const nm = ctx.raw && ctx.raw.feature && ctx.raw.feature.properties.name;
            return ` ${nm}: ${v.toLocaleString()} deal${v === 1 ? '' : 's'}`;
          } } },
        },
        scales: {
          projection: { axis: "x", projection: "albersUsa" },
          color: {
            axis: "x",
            domain: [0, max],
            interpolate: (t) => `rgba(0,162,72,${(0.10 + 0.90 * (t || 0)).toFixed(3)})`,
            legend: { display: false },
          },
        },
      },
    });
    showStateFallback(false);
  } catch (e){
    showStateFallback(true);                        // map couldn't render → show the list instead
  }
}

// Click-through panel for a state — Total Deals, Enrolled %, and its carrier + agent breakdown.
function renderStateDetail(obj){
  const el = $("#stateDetail");
  if (!el) return;
  if (!obj){ el.innerHTML = '<div class="cd-hint">Click a state for its breakdown</div>'; return; }
  const total = obj.count || 0, enr = obj.enrolled || 0;
  const pct = total ? (enr / total * 100).toFixed(1) : "0.0";
  const cars = (obj.carriers || []).slice(0, 6).map(c => `${c.label} ${c.count}`).join(" · ") || "—";
  const ags = (obj.agents || []).slice(0, 6).map(a => `${a.name} ${a.count}`).join(" · ") || "—";
  el.innerHTML = `
    <div class="cd-name">${STATE_NAME[obj.state] || obj.state}</div>
    <div class="cd-stats">
      <div><div class="cd-v">${total.toLocaleString()}</div><div class="cd-l">Total Deals</div></div>
      <div><div class="cd-v">${enr.toLocaleString()}</div><div class="cd-l">Enrolled · ${pct}%</div></div>
    </div>
    <div class="sd-row"><span class="sd-k">Carriers</span>${cars}</div>
    <div class="sd-row"><span class="sd-k">Agents</span>${ags}</div>`;
}

function renderEnrollments(e) {
  e = e || {total: 0, by_enroller: []};
  $("#enrollTotal").textContent = (e.total || 0).toLocaleString();
  const list = e.by_enroller || [];
  enrollById = {};
  list.forEach(g => enrollById[g.fronter_id] = g);
  $("#enrollList").innerHTML = list.length
    ? list.map(g => `
      <div class="enroll-row${g.fronter_id === selectedEnroller ? ' sel' : ''}" data-fid="${g.fronter_id}"><span class="enroll-name">${g.name ?? g.fronter_id}</span><span class="enroll-count">${(g.count || 0).toLocaleString()}</span></div>`).join("")
    : '<div class="dash" style="padding:10px 2px">No enrollments yet</div>';
  renderEnrollmentDetail(selectedEnroller && enrollById[selectedEnroller] ? enrollById[selectedEnroller] : null);
}

// Click-through: an enroller's breakdown — who they enrolled for (agent), carrier, and amount.
function renderEnrollmentDetail(en){
  const el = $("#enrollDetail");
  if (!el) return;
  if (!en){ el.innerHTML = '<div class="cd-hint">Click an enroller for their breakdown</div>'; return; }
  const detail = en.detail || [];
  const rows = detail.length
    ? detail.map(d => `<div class="ed-row"><span>${d.agent} · ${d.carrier}</span><b>${(d.count || 0).toLocaleString()}</b></div>`).join("")
    : '<div class="dash">No detail.</div>';
  el.innerHTML = `<div class="cd-name">${en.name || en.fronter_id} · ${en.count} enrolled</div><div class="ed-list">${rows}</div>`;
}

function renderRecent(rows) {
  lastRecentRows = rows || [];
  renderRecentRows();
}

/* Sales-table sorting. Same rules as the other tables: text A→Z first, dates/money
   newest-or-highest first, blanks last. Sorts rows already loaded, so it's instant. */
function sortRecentRows(rows){
  const k = recentSortKey, dir = recentSortDir;
  const numeric = (k === "agent_commission" || k === "fronter_commission" || k === "lead_id");
  return [...(rows || [])].sort((a, b) => {
    const x = a[k], y = b[k];
    const xb = x === "" || x == null, yb = y === "" || y == null;
    if (xb !== yb) return xb ? 1 : -1;
    if (xb && yb) return 0;
    if (numeric) return dir * ((Number(x) || 0) - (Number(y) || 0));
    return dir * String(x).localeCompare(String(y));
  });
}
function updateRecentSortArrows(){
  document.querySelectorAll("th[data-rsort]").forEach(th => {
    if (!th.dataset.label) th.dataset.label = th.textContent.trim();
    const active = th.getAttribute("data-rsort") === recentSortKey;
    th.classList.toggle("sorted", active);
    th.textContent = th.dataset.label + (active ? (recentSortDir === 1 ? " ▲" : " ▼") : "");
  });
}
function renderRecentRows(){
  updateRecentSortArrows();
  // commission is always set before submission, so a blank means "not in this pull" → em dash
  const money = v => (v === null || v === undefined || v === "")
    ? '<span class="dash">—</span>'
    : '$' + Number(v).toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2});
  const rows = sortRecentRows(lastRecentRows);
  const n = rows.length;
  $("#recentCount").textContent = n ? ` · ${n.toLocaleString()} ${n === 1 ? "sale" : "sales"}` : "";
  $("#recent").innerHTML = n ? rows.map(r => {
    const date = r.date_sold ? String(r.date_sold).split(" ")[0] : "";
    const enroller = r.enroller ? r.enroller : '<span class="dash">—</span>';
    return `
    <tr>
      <td>${date}</td>
      <td>${r.lead_id ?? ""}</td>
      <td>${r.agent || '<span class="dash">—</span>'}</td><td class="num col-sep">${money(r.agent_commission)}</td>
      <td>${enroller}</td><td class="num col-sep">${money(r.fronter_commission)}</td>
      <td>${r.carrier ?? ""}</td>
    </tr>`;
  }).join("")
   : '<tr><td colspan="7" class="dash" style="padding:14px">No sales in this range.</td></tr>';
}
document.querySelectorAll("th[data-rsort]").forEach(th => {
  th.addEventListener("click", () => {
    const k = th.getAttribute("data-rsort");
    if (recentSortKey === k) recentSortDir *= -1;
    else { recentSortKey = k;
           recentSortDir = (k === "date_sold" || k === "lead_id"
                            || k.endsWith("commission")) ? -1 : 1; }
    renderRecentRows();
  });
});

// Active Policies by carrier — in-force count, total sold, retention % per carrier.
// Click a carrier row to see its active policies broken down by state.
function renderActive(rows){
  rows = rows || [];
  activeByCarrier = {};
  rows.forEach(r => activeByCarrier[r.carrier] = r);
  activeCombined = combinedActiveStates(rows);
  const totalActive = activeCombined.active, totalSold = activeCombined.sold;
  const pct = totalSold ? Math.round(totalActive / totalSold * 100) : 0;
  $("#activeTotal").textContent = totalActive.toLocaleString();
  $("#activeOfSold").textContent = totalSold ? `of ${totalSold.toLocaleString()} sold · ${pct}% still active` : "";
  const pctCell = (a, s) => s ? Math.round(a / s * 100) + "%" : "—";
  $("#activeList").innerHTML = rows.length
    ? rows.map(r => `<tr data-carrier="${r.carrier}"${r.carrier === selectedActiveCarrier ? ' class="sel"' : ''}>
        <td>${r.carrier}</td>
        <td class="num">${(r.active || 0).toLocaleString()}</td>
        <td class="num">${(r.sold || 0).toLocaleString()}</td>
        <td class="num">${pctCell(r.active, r.sold)}</td>
      </tr>`).join("")
    : '<tr><td colspan="4" class="dash" style="padding:14px">No policies in this range.</td></tr>';
  $("#activeTotals").innerHTML = rows.length
    ? `<tr><td>Totals</td><td class="num">${totalActive.toLocaleString()}</td><td class="num">${totalSold.toLocaleString()}</td><td class="num">${pct}%</td></tr>`
    : "";
  // no carrier selected -> combined total by state; otherwise that carrier
  const sel = (selectedActiveCarrier && activeByCarrier[selectedActiveCarrier]) ? activeByCarrier[selectedActiveCarrier] : activeCombined;
  renderActiveDetail(sel);
}

// Aggregate active-by-state across ALL carriers — the default view when none is selected.
function combinedActiveStates(rows){
  const agg = {};
  let active = 0, sold = 0;
  (rows || []).forEach(r => {
    active += r.active || 0; sold += r.sold || 0;
    (r.states || []).forEach(s => {
      const a = agg[s.state] || (agg[s.state] = {state: s.state, active: 0, sold: 0});
      a.active += s.active || 0; a.sold += s.sold || 0;
    });
  });
  return {carrier: "All carriers", active, sold, states: Object.values(agg).sort((x, y) => y.active - x.active)};
}

// Click-through: a carrier's active policies broken down by state (active / sold per state).
function renderActiveDetail(c){
  const el = $("#activeDetail");
  if (!el) return;
  if (!c){ el.innerHTML = '<div class="cd-hint">Click a carrier for its active policies by state</div>'; return; }
  const states = c.states || [];
  const body = states.length
    ? states.map(s => `<span class="ad-st">${s.state} <b>${(s.active || 0).toLocaleString()}</b><span class="sub">/${(s.sold || 0).toLocaleString()}</span></span>`).join("")
    : '<span class="dash">No state data.</span>';
  el.innerHTML = `<div class="cd-name">${c.carrier} · active by state <span class="cd-sub">(active / sold)</span></div><div class="ad-list">${body}</div>`;
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
      <td class="num">${wait(a.cpa, money2)}</td>
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
      <td class="num">${t ? money2(t.cpa) : '…'}</td>
    </tr>`;
}

/* ===== Sales Board (own date range + collapsible) ===== */
function boardMsg(t){ return `<tr><td colspan="7" class="dash" style="padding:14px">${t}</td></tr>`; }
async function boardLoad(){
  const list = $("#boardList");
  if (!list) return;
  if (boardAuto){                                   // always keep the board on this week-to-date
    const today = new Date(); today.setHours(0,0,0,0);
    setPicker(fpById["boardStart"], "boardStart", startOfWeek(today));
    setPicker(fpById["boardEnd"], "boardEnd", today);
  }
  const s = pickerISO("boardStart"), e = pickerISO("boardEnd");
  if (!s || !e){ list.innerHTML = boardMsg("Pick a start and end date."); return; }
  if (e < s){ list.innerHTML = boardMsg("End date can’t be before the start date."); return; }
  try {
    const carrier = $("#boardCarrier") ? $("#boardCarrier").value : "";
    const qs = `range=custom&start=${s}&end=${e}` + (carrier ? `&carrier=${encodeURIComponent(carrier)}` : "");
    const res = await fetch(`/api/sales_board?${qs}`);
    const data = await res.json();
    if (data.error && !data.board){ list.innerHTML = boardMsg(data.error); return; }
    renderBoard(data);
  } catch (err) { list.innerHTML = boardMsg("Could not load the sales board."); }
}
function renderBoard(data){
  lastBoard = data;                                  // keep it so sorting can re-render without a refetch
  $("#boardLabel").textContent = data.range_label || "";
  populateBoardCarriers(data.carriers || []);
  updateBoardSortArrows();
  const rows = sortBoardRows(data.board || []);
  const fmt = n => (n || 0).toLocaleString();
  const money = v => '$' + Number(v || 0).toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2});
  $("#boardList").innerHTML = rows.length ? rows.map((p, i) => {
    const top = (p.carriers || []).slice(0, 4).map(c => `${c.label} ${c.count}`).join(" · ");
    const more = (p.carriers || []).length > 4 ? " …" : "";
    return `<tr data-person="${p.name}" title="Click for this person's deals">
      <td><span class="rank ${i === 0 ? 'top' : ''}">${i + 1}</span></td>
      <td>${p.name}</td>
      <td class="num">${fmt(p.closed)}</td>
      <td class="num">${fmt(p.enrolled)}</td>
      <td class="num"><b>${fmt(p.total)}</b></td>
      <td class="num">${money(p.commission)}</td>
      <td class="bd-car">${top ? top + more : '<span class="dash">—</span>'}</td>
    </tr>`;
  }).join("") : boardMsg("No deals in this range.");
}
/* Board sorting — client-side, so it never refetches. Numbers sort high→low on the first
   click, names A→Z; clicking the same column again reverses. Uses its own state + the
   data-bsort attribute so it can't collide with the Agent Performance table's sorting. */
function sortBoardRows(rows){
  const k = boardSortKey;
  return [...(rows || [])].sort((a, b) => {
    if (k === "name") return boardSortDir * String(a.name || "").localeCompare(String(b.name || ""));
    const d = (a[k] || 0) - (b[k] || 0);
    return boardSortDir * (d || 0) || String(a.name || "").localeCompare(String(b.name || ""));  // ties: by name
  });
}
function updateBoardSortArrows(){
  document.querySelectorAll("th[data-bsort]").forEach(th => {
    if (!th.dataset.label) th.dataset.label = th.textContent.trim();   // remember the plain header text
    const active = th.getAttribute("data-bsort") === boardSortKey;
    th.classList.toggle("sorted", active);
    th.textContent = th.dataset.label + (active ? (boardSortDir === 1 ? " ▲" : " ▼") : "");
  });
}
document.querySelectorAll("th[data-bsort]").forEach(th => {
  th.addEventListener("click", () => {
    const k = th.getAttribute("data-bsort");
    if (boardSortKey === k) boardSortDir *= -1;                 // same column -> flip direction
    else { boardSortKey = k; boardSortDir = (k === "name") ? 1 : -1; }   // name A→Z, numbers high→low
    if (lastBoard) renderBoard(lastBoard);
    else updateBoardSortArrows();
  });
});

// Fill the board's carrier dropdown from the range's carriers, preserving the current pick.
function populateBoardCarriers(carriers){
  const sel = $("#boardCarrier"); if (!sel) return;
  const existing = Array.from(sel.options).slice(1).map(o => o.value);
  if (existing.length === carriers.length && existing.every((v, i) => v === carriers[i])) return;
  const cur = sel.value;
  sel.innerHTML = ['<option value="">All carriers</option>'].concat(carriers.map(c => `<option value="${c}">${c}</option>`)).join("");
  sel.value = carriers.includes(cur) ? cur : "";
}
function toggleBoard(){
  boardOpen = !boardOpen;
  $("#boardSection").classList.toggle("collapsed", !boardOpen);
  $("#boardToggle").setAttribute("aria-expanded", boardOpen ? "true" : "false");
  if (boardOpen) boardLoad();
}

/* ===== Agent Detail tab — every deal a person closed or enrolled, with the SEP ===== */
function showTab(which){
  const views = {dashboard: "#viewDashboard", detail: "#viewDetail", vendors: "#viewVendors"};
  const tabs = {dashboard: "#tabDashboard", detail: "#tabDetail", vendors: "#tabVendors"};
  Object.keys(views).forEach(k => {
    $(views[k]).hidden = (k !== which);
    $(tabs[k]).classList.toggle("active", k === which);
  });
  closeRelMenu();
  if (which === "detail" && !$("#detailStart").value){   // first visit: inherit the board's range
    setPicker(fpById["detailStart"], "detailStart", parseDateInput($("#boardStart").value) || new Date());
    setPicker(fpById["detailEnd"], "detailEnd", parseDateInput($("#boardEnd").value) || new Date());
    loadDetail();
  }
  if (which === "vendors" && !$("#vendorStart").value){
    const today = new Date(); today.setHours(0,0,0,0);
    setPicker(fpById["vendorStart"], "vendorStart", startOfWeek(today));
    setPicker(fpById["vendorEnd"], "vendorEnd", today);
    loadVendors();
  }
}

/* ===== Vendors tab ===== */
function vendorRange(){
  return {s: pickerISO("vendorStart"), e: pickerISO("vendorEnd"),
          v: $("#vendorPick") ? $("#vendorPick").value : ""};
}
async function loadVendors(){
  const {s, e, v} = vendorRange();
  const sum = $("#vendorSummary");
  if (!s || !e){ sum.textContent = "Pick a start and end date."; return; }
  if (e < s){ sum.textContent = "End date can’t be before the start date."; return; }
  sum.textContent = "Loading…";
  $("#dispoWrap").hidden = true;                        // dispo is per-range; make them re-load
  try {
    const qs = `range=custom&start=${s}&end=${e}` + (v ? `&vendor_id=${encodeURIComponent(v)}` : "");
    const d = await fetch(`/api/vendors?${qs}`).then(r => r.json());
    if (d.error){ sum.textContent = d.error; return; }
    renderVendors(d);
    loadVendorCost(s, e, v);          // slow report — fills in behind the lead table
  } catch (err){ sum.textContent = "Could not load vendor data."; }
}

// Spend / CPA for the chosen vendor. Uses report_cpa_agent's costs_all, which is the
// billed figure (verified against a real invoice); vendorperformance's Spend is leads-based
// and reads ~39% low, so it is deliberately not used here.
async function loadVendorCost(s, e, v){
  const box = $("#vendorCost");
  if (!box) return;
  const card = (label, val, note) =>
    `<div class="kpi"><div class="label">${label}</div><div class="value">${val}</div>
     <div class="delta note">${note || ""}</div></div>`;
  box.innerHTML = card("Spend", "…", "loading the cost report")
                + card("Sales", "…", "") + card("CPA", "…", "");
  try {
    const qs = `range=custom&start=${s}&end=${e}&cost=1` + (v ? `&vendor_id=${encodeURIComponent(v)}` : "");
    const d = await fetch(`/api/vendors?${qs}`).then(r => r.json());
    const c = d.cost;
    if (!c){ box.innerHTML = ""; return; }
    const who = v ? ($("#vendorPick").selectedOptions[0] || {}).text || "vendor" : "all vendors";
    const free = c.spend === 0;
    box.innerHTML =
        card("Spend", money2(c.spend), `${who} · billable calls x price`)
      + card("Sales", (c.sales || 0).toLocaleString(), `${(c.calls_billable || 0).toLocaleString()} billable calls`)
      + card("CPA", free ? '<span class="dash">—</span>' : money2(c.cpa),
             free ? "no lead cost — worked from existing leads" : "spend ÷ sales");
  } catch (err){ box.innerHTML = ""; }
}
function renderVendors(d){
  const cat = {};
  (d.vendors || []).forEach(v => cat[v.vendor_id] = v);
  fillVendorPicker(d.vendors || [], d.leads || {});
  const rows = (d.leads && d.leads.by_vendor) || [];
  const t = (d.leads && d.leads.totals) || {};
  const fmt = n => (n || 0).toLocaleString();
  const pct = (a, b) => b ? (a / b * 100).toFixed(1) + "%" : '<span class="dash">—</span>';
  $("#vendorSummary").innerHTML = rows.length
    ? `<b>${fmt(t.leads)}</b> leads · <b>${fmt(t.billable)}</b> billable · <b>${fmt(t.sold)}</b> produced a policy`
    : "No leads in this range.";
  $("#vendorRows").innerHTML = rows.length ? rows.map(r => {
    const c = cat[r.vendor_id] || {};
    const price = c.price_inbound || c.price;
    return `<tr>
      <td>${r.vendor}</td>
      <td class="num">${fmt(r.leads)}</td>
      <td class="num">${fmt(r.billable)}</td>
      <td class="num">${fmt(r.sold)}</td>
      <td class="num">${pct(r.sold, r.billable)}</td>
      <td class="num">${price ? "$" + Number(price).toFixed(2) : '<span class="dash">—</span>'}</td>
      <td class="bd-car">${c.status || ""}</td>
    </tr>`;
  }).join("") : '<tr><td colspan="7" class="dash" style="padding:14px">No leads in this range.</td></tr>';
  $("#vendorTotals").innerHTML = rows.length
    ? `<tr><td>Totals</td><td class="num">${fmt(t.leads)}</td><td class="num">${fmt(t.billable)}</td><td class="num">${fmt(t.sold)}</td><td class="num">${pct(t.sold, t.billable)}</td><td></td><td></td></tr>` : "";
}
// The picker lists vendors WITH ACTIVITY first — the status flag can't be trusted
// (FALCON is marked "inactive" while doing ~99% of the volume).
function fillVendorPicker(catalogue, leads){
  const sel = $("#vendorPick"); if (!sel) return;
  const active = new Set((leads.by_vendor || []).map(v => String(v.vendor_id)));
  const withData = catalogue.filter(v => active.has(String(v.vendor_id)));
  const rest = catalogue.filter(v => !active.has(String(v.vendor_id)));
  const opt = v => `<option value="${v.vendor_id}">${v.name}</option>`;
  const cur = sel.value;
  sel.innerHTML = '<option value="">All vendors</option>'
    + (withData.length ? `<optgroup label="Active in this range">${withData.map(opt).join("")}</optgroup>` : "")
    + (rest.length ? `<optgroup label="No activity in this range">${rest.map(opt).join("")}</optgroup>` : "");
  sel.value = cur;
}
// Invoice audit — the calls you were billed for, and what each one produced. The headline
// is money spent on calls nobody answered, which is invisible in any report total.
async function loadBilled(){
  const {s, e, v} = vendorRange();
  const sum = $("#billedSummary");
  if (!s || !e){ sum.textContent = "Pick a start and end date first."; return; }
  sum.textContent = "Loading billed calls…";
  try {
    const qs = `range=custom&start=${s}&end=${e}&billed=1` + (v ? `&vendor_id=${encodeURIComponent(v)}` : "");
    const d = await fetch(`/api/vendors?${qs}`).then(r => r.json());
    const b = d.billed;
    if (!b){ sum.textContent = "Could not load billed calls."; return; }
    const t = b.summary || {};
    const money = n => "$" + Number(n || 0).toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2});
    const card = (label, val, note, warn) =>
      `<div class="kpi"><div class="label">${label}</div>
       <div class="value"${warn ? ' style="color:#E2574C"' : ""}>${val}</div>
       <div class="delta note">${note || ""}</div></div>`;
    // "Converted" = a billed call whose LEAD produced a policy. It is NOT the day's total
    // sales — a sale can come from a call you weren't billed for — so the label says so.
    $("#billedKpis").innerHTML =
        card("Billed Calls", (t.calls || 0).toLocaleString(), money(t.spend) + " total")
      + card("Converted", (t.sales || 0).toLocaleString(),
             t.sales
               ? money(t.cost_per_sale) + " per policy"
                 + (t.converted_calls > t.sales ? ` · from ${t.converted_calls} billed calls` : "")
               : "none linked to a policy")
      + card("Paid but not answered", (t.dropped || 0).toLocaleString(),
             `${money(t.dropped_cost)} · ${t.dropped_pct}% of billed calls`, (t.dropped || 0) > 0);
    sum.innerHTML = `<b>${(t.calls || 0).toLocaleString()}</b> billed calls · <b>${money(t.spend)}</b>`
      + (b.unhandled_statuses && b.unhandled_statuses.length
          ? ` <span class="dash">(counted as unanswered: ${b.unhandled_statuses.join(", ")})</span>` : "");
    lastBilledRows = b.rows || [];
    renderBilledRows();
    $("#billedWrap").hidden = false;
    $("#billedExport").hidden = !lastBilledRows.length;
  } catch (err){ sum.textContent = "Could not load billed calls."; }
}

/* Invoice-audit sorting — click a column, click again to reverse. Text goes A→Z first,
   numbers and dates high/newest first. Blanks sink to the bottom, so sorting by Agent
   groups the real names together instead of burying them under unanswered calls.
   Uses data-isort so it can't collide with the other three sortable tables. */
function sortBilledRows(rows){
  const k = billedSortKey, dir = billedSortDir;
  const numeric = (k === "talk_sec" || k === "cost");
  return [...(rows || [])].sort((a, b) => {
    const x = a[k], y = b[k];
    const xb = x === "" || x == null, yb = y === "" || y == null;
    if (xb !== yb) return xb ? 1 : -1;                 // blanks last, either direction
    if (xb && yb) return 0;
    if (numeric) return dir * ((Number(x) || 0) - (Number(y) || 0));
    return dir * String(x).localeCompare(String(y));
  });
}
function updateBilledSortArrows(){
  document.querySelectorAll("th[data-isort]").forEach(th => {
    if (!th.dataset.label) th.dataset.label = th.textContent.trim();
    const active = th.getAttribute("data-isort") === billedSortKey;
    th.classList.toggle("sorted", active);
    th.textContent = th.dataset.label + (active ? (billedSortDir === 1 ? " ▲" : " ▼") : "");
  });
}
function renderBilledRows(){
  updateBilledSortArrows();
  const money = n => "$" + Number(n || 0).toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2});
  const rows = sortBilledRows(lastBilledRows);
  $("#billedRows").innerHTML = rows.length ? rows.slice(0, 3000).map(r => `
      <tr>
        <td>${(r.call_date || "").replace("T", " ")}</td>
        <td>${r.vendor || ""}</td>
        <td>${r.agent || '<span class="dash">—</span>'}</td>
        <td${/no agent|not available|timeout|after hours|drop/i.test(r.status) ? ' style="color:#E2574C;font-weight:600"' : ""}>${r.status || ""}</td>
        <td class="num">${r.talk_sec ? Math.round(r.talk_sec) + "s" : '<span class="dash">—</span>'}</td>
        <td class="num">${money(r.cost)}</td>
        <td title="${r.dialer_lead_id ? "dialer id " + r.dialer_lead_id : ""}">${r.lead_id || '<span class="dash">—</span>'}${r.converted ? ' <span title="this lead produced a policy" style="color:#00A248;font-weight:700">✓</span>' : ""}</td>
      </tr>`).join("")
    : '<tr><td colspan="7" class="dash" style="padding:14px">No billed calls in this range.</td></tr>';
}
document.querySelectorAll("th[data-isort]").forEach(th => {
  th.addEventListener("click", () => {
    const k = th.getAttribute("data-isort");
    if (billedSortKey === k) billedSortDir *= -1;                        // same column -> flip
    else { billedSortKey = k; billedSortDir = (k === "call_date" || k === "talk_sec" || k === "cost") ? -1 : 1; }
    renderBilledRows();
  });
});

async function loadDispo(){
  const {s, e, v} = vendorRange();
  const sum = $("#dispoSummary");
  if (!s || !e){ sum.textContent = "Pick a start and end date first."; return; }
  sum.textContent = "Loading dispositions… (first look at a long range takes a moment)";
  try {
    const dir = $("#dispoDirection") ? $("#dispoDirection").value : "INBOUND";
    const qs = `range=custom&start=${s}&end=${e}&dispo=1&direction=${dir}`
      + (v ? `&vendor_id=${encodeURIComponent(v)}` : "");
    const d = await fetch(`/api/vendors?${qs}`).then(r => r.json());
    const dp = d.dispo;
    if (!dp){ sum.textContent = "Could not load dispositions."; return; }
    const rows = dp.dispositions || [];
    const total = dp.total || 0;
    const label = dir === "INBOUND" ? "inbound calls" : dir === "OUTBOUND" ? "outbound calls" : "calls";
    sum.innerHTML = `<b>${total.toLocaleString()}</b> ${label} over ${dp.days} day(s)`
      + (dp.filtered_spam ? ` · <span class="dash">${dp.filtered_spam.toLocaleString()} robocalls excluded (caught by TLD's filter)</span>` : "")
      + (dp.cached_days ? ` · ${dp.cached_days} day(s) from saved data` : "");
    const max = Math.max(1, ...rows.map(r => r.count));
    $("#dispoRows").innerHTML = rows.map(r => `
      <tr>
        <td>${r.status}</td>
        <td class="num">${r.count.toLocaleString()}</td>
        <td class="num">${total ? (r.count / total * 100).toFixed(1) + "%" : "—"}</td>
        <td><div class="bar-track" style="min-width:120px"><div class="bar-fill" style="width:${(r.count / max * 100).toFixed(0)}%"></div></div></td>
      </tr>`).join("");
    $("#dispoWrap").hidden = false;
    $("#dispoExport").hidden = !rows.length;
  } catch (err){ sum.textContent = "Could not load dispositions."; }
}

async function loadDetail(agent){
  const s = pickerISO("detailStart"), e = pickerISO("detailEnd");
  const body = $("#detailRows"), sum = $("#detailSummary");
  if (!s || !e){ sum.textContent = "Pick a start and end date."; return; }
  if (e < s){ sum.textContent = "End date can’t be before the start date."; return; }
  const who = agent !== undefined ? agent : $("#detailAgent").value;
  sum.textContent = "Loading…";
  body.innerHTML = "";
  try {
    const qs = `range=custom&start=${s}&end=${e}` + (who ? `&agent=${encodeURIComponent(who)}` : "");
    const d = await fetch(`/api/agent_detail?${qs}`).then(r => r.json());
    if (d.error){ sum.textContent = d.error; return; }
    fillDetailPeople(d.people || [], who);
    if (!who){
      sum.innerHTML = `Pick a person above to see their deals · <b>${(d.people || []).length}</b> people in this range`;
      return;
    }
    const t = d.summary || {};
    sum.innerHTML = `<b>${who}</b> · closed <b>${t.closed || 0}</b> · enrolled <b>${t.enrolled || 0}</b> · total <b>${t.total || 0}</b>`;
    lastDetailRows = d.rows || [];
    renderDetailRows();
    renderDetailStates(d.by_state || [], t.total || 0);
  } catch (err) {
    sum.textContent = "Could not load the agent detail.";
  }
}

/* Detail table sorting — click a column to sort, click again to reverse. Text columns go
   A→Z first, dates/ids newest-or-highest first. Blanks always sink to the bottom so an
   empty SEP or self-enrolled row never buries the real values. Sorts in place, no refetch. */
function sortDetailRows(rows){
  const k = detailSortKey, dir = detailSortDir;
  return [...(rows || [])].sort((a, b) => {
    const x = a[k] ?? "", y = b[k] ?? "";
    const xb = x === "" || x == null, yb = y === "" || y == null;
    if (xb !== yb) return xb ? 1 : -1;                       // blanks last, either direction
    if (xb && yb) return 0;
    if (k === "lead_id") return dir * ((Number(x) || 0) - (Number(y) || 0));
    return dir * String(x).localeCompare(String(y));
  });
}
function updateDetailSortArrows(){
  document.querySelectorAll("th[data-dsort]").forEach(th => {
    if (!th.dataset.label) th.dataset.label = th.textContent.trim();
    const active = th.getAttribute("data-dsort") === detailSortKey;
    th.classList.toggle("sorted", active);
    th.textContent = th.dataset.label + (active ? (detailSortDir === 1 ? " ▲" : " ▼") : "");
  });
}
function renderDetailRows(){
  updateDetailSortArrows();
  const rows = sortDetailRows(lastDetailRows);
  $("#detailRows").innerHTML = rows.length ? rows.map(r => `
      <tr>
        <td>${r.date_sold || ""}</td>
        <td>${r.lead_id ?? ""}</td>
        <td><span class="pill-role ${r.role}">${r.role}</span></td>
        <td>${r.agent || '<span class="dash">—</span>'}</td>
        <td>${r.enroller || '<span class="dash">—</span>'}</td>
        <td>${r.state || '<span class="dash">—</span>'}</td>
        <td>${r.carrier || ""}</td>
        <td>${r.plan || '<span class="dash">—</span>'}</td>
        <td class="sep-tag">${r.sep || '<span class="dash">—</span>'}</td>
      </tr>`).join("")
    : '<tr><td colspan="9" class="dash" style="padding:14px">No deals for this person in this range.</td></tr>';
}

// Where this person's business comes from. Split by role because someone can close in one
// set of states and enrol in another — a blended total would hide that.
function renderDetailStates(states, total){
  const el = $("#detailStates");
  if (!el) return;
  const max = Math.max(1, ...states.map(s => s.total || 0));
  el.innerHTML = states.length ? states.map(s => `
    <tr>
      <td>${s.state}</td>
      <td class="num">${(s.closed || 0).toLocaleString()}</td>
      <td class="num">${(s.enrolled || 0).toLocaleString()}</td>
      <td class="num"><b>${(s.total || 0).toLocaleString()}</b></td>
      <td class="num">${total ? (s.total / total * 100).toFixed(1) + "%" : "—"}</td>
      <td><div class="bar-track" style="min-width:110px"><div class="bar-fill" style="width:${(s.total / max * 100).toFixed(0)}%"></div></div></td>
    </tr>`).join("")
    : '<tr><td colspan="6" class="dash" style="padding:14px">Pick a person to see where their deals come from.</td></tr>';
}
document.querySelectorAll("th[data-dsort]").forEach(th => {
  th.addEventListener("click", () => {
    const k = th.getAttribute("data-dsort");
    if (detailSortKey === k) detailSortDir *= -1;                     // same column -> flip
    else { detailSortKey = k; detailSortDir = (k === "date_sold" || k === "lead_id") ? -1 : 1; }
    renderDetailRows();
  });
});

// One person's dispositions for the dates shown. Filtered server-side by name, so it's a
// small fast query — no caching needed. "System Process" is a separate user, so automated
// activity never lands in a person's numbers.
async function loadAgentDispo(){
  const who = $("#detailAgent").value;
  const s = pickerISO("detailStart"), e = pickerISO("detailEnd");
  const sum = $("#agentDispoSummary");
  if (!who){ sum.textContent = "Pick a person above first."; return; }
  if (!s || !e){ sum.textContent = "Pick a start and end date."; return; }
  sum.textContent = "Loading dispositions…";
  $("#agentDispoWrap").hidden = true;
  try {
    const d = await fetch(`/api/agent_detail?range=custom&start=${s}&end=${e}`
      + `&agent=${encodeURIComponent(who)}&dispo=1`).then(r => r.json());
    const dp = d.dispo || {};
    const rows = dp.dispositions || [];
    const total = dp.total || 0;
    if (!rows.length){
      // be explicit: nothing found vs. a name that never matched
      sum.innerHTML = `No dispositions found for <b>${who}</b> in this range`
        + (dp.searched ? ` <span class="dash">(searched: ${dp.searched.join(" / ")})</span>` : "");
      return;
    }
    sum.innerHTML = `<b>${who}</b> · <b>${total.toLocaleString()}</b> dispositions`;
    const max = Math.max(1, ...rows.map(r => r.count));
    $("#agentDispoRows").innerHTML = rows.map(r => `
      <tr>
        <td>${r.status}</td>
        <td class="num">${r.count.toLocaleString()}</td>
        <td class="num">${(r.count / total * 100).toFixed(1)}%</td>
        <td><div class="bar-track" style="min-width:120px"><div class="bar-fill" style="width:${(r.count / max * 100).toFixed(0)}%"></div></div></td>
      </tr>`).join("");
    $("#agentDispoWrap").hidden = false;
    $("#agentDispoExport").hidden = false;
  } catch (err){ sum.textContent = "Could not load dispositions."; }
}

function fillDetailPeople(people, selected){
  const sel = $("#detailAgent");
  const cur = selected !== undefined ? selected : sel.value;
  const existing = Array.from(sel.options).slice(1).map(o => o.value);
  if (existing.length !== people.length || !existing.every((v, i) => v === people[i])){
    sel.innerHTML = ['<option value="">Choose a person…</option>']
      .concat(people.map(p => `<option value="${p}">${p}</option>`)).join("");
  }
  sel.value = people.includes(cur) ? cur : "";
}

// Jump from the sales board straight into a person's breakdown, same dates.
function openAgentDetail(name){
  setPicker(fpById["detailStart"], "detailStart", parseDateInput($("#boardStart").value) || new Date());
  setPicker(fpById["detailEnd"], "detailEnd", parseDateInput($("#boardEnd").value) || new Date());
  showTab("detail");
  window.scrollTo({top: 0, behavior: "smooth"});
  loadDetail(name);
}

/* ---- GUI events ---- */
$("#tabDashboard").addEventListener("click", () => showTab("dashboard"));
$("#tabDetail").addEventListener("click", () => showTab("detail"));
$("#tabVendors").addEventListener("click", () => showTab("vendors"));
$("#vendorApply").addEventListener("click", loadVendors);
$("#vendorPick").addEventListener("change", loadVendors);
$("#vendorExport").addEventListener("click", () => {
  const {s, e, v} = vendorRange();
  if (!s || !e) return;
  window.location = `/api/vendors/export?range=custom&start=${s}&end=${e}`
    + (v ? `&vendor_id=${encodeURIComponent(v)}` : "");
});
$("#billedLoad").addEventListener("click", loadBilled);
$("#billedExport").addEventListener("click", () => {
  const {s, e, v} = vendorRange();
  window.location = `/api/vendors/billed/export?range=custom&start=${s}&end=${e}`
    + (v ? `&vendor_id=${encodeURIComponent(v)}` : "");
});
$("#dispoLoad").addEventListener("click", loadDispo);
$("#dispoDirection").addEventListener("change", () => { if (!$("#dispoWrap").hidden) loadDispo(); });
$("#dispoExport").addEventListener("click", () => {
  const {s, e, v} = vendorRange();
  const dir = $("#dispoDirection").value;
  window.location = `/api/vendors/dispo/export?range=custom&start=${s}&end=${e}&direction=${dir}`
    + (v ? `&vendor_id=${encodeURIComponent(v)}` : "");
});
$("#agentDispoExport").addEventListener("click", () => {
  const who = $("#detailAgent").value;
  const s = pickerISO("detailStart"), e = pickerISO("detailEnd");
  if (!who) return;
  window.location = `/api/agent_detail/dispo/export?range=custom&start=${s}&end=${e}`
    + `&agent=${encodeURIComponent(who)}`;
});
["vendorStart","vendorEnd"].forEach(id => { const el = $("#"+id);
  if (el) el.addEventListener("keydown", ev => { if (ev.key === "Enter") loadVendors(); }); });
$("#detailApply").addEventListener("click", () => loadDetail());
$("#detailExport").addEventListener("click", () => {
  const who = $("#detailAgent").value;
  const s = pickerISO("detailStart"), e = pickerISO("detailEnd");
  if (!who){ $("#detailSummary").textContent = "Choose a person before exporting."; return; }
  if (!s || !e){ $("#detailSummary").textContent = "Pick a start and end date."; return; }
  // hand the server the sort we're currently showing so the file matches the screen
  window.location = `/api/agent_detail/export?range=custom&start=${s}&end=${e}`
    + `&agent=${encodeURIComponent(who)}&sort=${detailSortKey}&dir=${detailSortDir}`;
});
$("#detailAgent").addEventListener("change", () => { loadDetail(); $("#agentDispoWrap").hidden = true;
  $("#agentDispoSummary").textContent = "Load dispositions for this person."; });
$("#activeExport").addEventListener("click", () => {
  const sel = currentSel();
  if (sel.key === "custom" && !validCustom(sel)) return;
  window.location = `/api/active/export?${qsFor(sel)}`;
});
$("#stateExport").addEventListener("click", () => {
  const sel = currentSel();
  if (sel.key === "custom" && !validCustom(sel)) return;
  const withAgents = $("#stateIncludeAgents").checked ? "&agents=1" : "";
  window.location = `/api/state/export?${qsFor(sel)}${withAgents}`;
});
$("#agentDispoLoad").addEventListener("click", loadAgentDispo);
["detailStart","detailEnd"].forEach(id => { const el = $("#"+id);
  if (el) el.addEventListener("keydown", ev => { if (ev.key === "Enter") loadDetail(); }); });
$("#boardList").addEventListener("click", e => {          // click a name on the board -> detail
  const tr = e.target.closest("tr[data-person]"); if (!tr) return;
  openAgentDetail(tr.getAttribute("data-person"));
});
$("#applyRange").addEventListener("click", () => load(true));
["startDate","endDate"].forEach(id => $("#"+id).addEventListener("keydown", e => { if (e.key === "Enter") load(true); }));
$("#refresh").addEventListener("click", () => { load(true); boardLoad(); });   // force a fully fresh pull
$("#autoRefresh").addEventListener("change", () => armAuto());
$("#stateList")?.addEventListener("click", e => {   // list fallback is clickable too
  const el = e.target.closest(".st"); if (!el) return;
  selectedState = el.getAttribute("data-state");
  renderStateDetail(stateByAbbr[selectedState]);
});
$("#activeList")?.addEventListener("click", e => {   // carrier row -> active by state (click again to deselect)
  const tr = e.target.closest("tr[data-carrier]"); if (!tr) return;
  const car = tr.getAttribute("data-carrier");
  selectedActiveCarrier = (selectedActiveCarrier === car) ? null : car;
  $("#activeList").querySelectorAll("tr").forEach(row =>
    row.classList.toggle("sel", !!selectedActiveCarrier && row.getAttribute("data-carrier") === selectedActiveCarrier));
  renderActiveDetail(selectedActiveCarrier ? activeByCarrier[selectedActiveCarrier] : activeCombined);
});
$("#boardCarrier")?.addEventListener("change", boardLoad);   // filter the sales board by carrier
$("#enrollList")?.addEventListener("click", e => {           // enroller -> who/carrier/amount (click again to close)
  const row = e.target.closest(".enroll-row"); if (!row) return;
  const fid = row.getAttribute("data-fid");
  selectedEnroller = (selectedEnroller === fid) ? null : fid;
  document.querySelectorAll("#enrollList .enroll-row").forEach(r =>
    r.classList.toggle("sel", !!selectedEnroller && r.getAttribute("data-fid") === selectedEnroller));
  renderEnrollmentDetail(selectedEnroller ? enrollById[selectedEnroller] : null);
});
$("#boardToggle").addEventListener("click", toggleBoard);
$("#boardApply").addEventListener("click", () => { boardAuto = false; boardLoad(); });
["boardStart","boardEnd"].forEach(id => { const el = $("#"+id); if (el) el.addEventListener("keydown", e => { if (e.key === "Enter") { boardAuto = false; boardLoad(); } }); });
document.querySelectorAll("th[data-sort]").forEach(th => {
  th.addEventListener("click", () => {
    const k = th.getAttribute("data-sort");
    if (sortKey === k) sortDir *= -1;
    else { sortKey = k; sortDir = (k === "name") ? 1 : -1; }
    if (lastData) renderAgents(lastData.agents);
  });
});

initDatePickers();
// Default to today's data on first load (main + board fields = today).
(function(){
  const today = new Date(); today.setHours(0,0,0,0);
  setPicker(fpStart, "startDate", today);
  setPicker(fpEnd, "endDate", today);
  setPicker(fpById["boardStart"], "boardStart", startOfWeek(today));   // board defaults to week-to-date
  setPicker(fpById["boardEnd"], "boardEnd", today);
})();
load();
