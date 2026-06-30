/* ============================================================
   GUI LAYER
   Fetches JSON from the Python backend (/api/dashboard) and renders it.
   No API keys, no TLDCRM calls here — that all lives in Python.
   ============================================================ */
const $ = s => document.querySelector(s);
const C = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();

let charts = {};          // keep chart instances so we can destroy before redraw
let selectedCarrier = null;  // carrier slice currently shown in the detail panel
let boardOpen = true;     // sales board expanded (true) or collapsed to its tab (false)
let boardAuto = true;     // board auto-anchors to this-week-to-date until the user picks a custom range
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
  [["startMenuBtn","startDate"], ["endMenuBtn","endDate"],
   ["boardStartMenuBtn","boardStart"], ["boardEndMenuBtn","boardEnd"]].forEach(([btn, fld]) => {
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
    if (boardOpen) boardLoad();     // refresh the sales board on the same cycle (uses its own range)
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
      onHover(evt, els){ if (evt.native) evt.native.target.style.cursor = els.length ? "pointer" : "default"; },
      onClick(evt, els){
        if (!els.length) return;
        const i = els[0].index;
        selectedCarrier = rows[i].label;
        renderCarrierDetail(rows[i], i);
      },
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
    const res = await fetch(`/api/sales_board?range=custom&start=${s}&end=${e}`);
    const data = await res.json();
    if (data.error && !data.board){ list.innerHTML = boardMsg(data.error); return; }
    renderBoard(data);
  } catch (err) { list.innerHTML = boardMsg("Could not load the sales board."); }
}
function renderBoard(data){
  $("#boardLabel").textContent = data.range_label || "";
  const rows = data.board || [];
  const fmt = n => (n || 0).toLocaleString();
  const money = v => '$' + Number(v || 0).toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2});
  $("#boardList").innerHTML = rows.length ? rows.map((p, i) => {
    const top = (p.carriers || []).slice(0, 4).map(c => `${c.label} ${c.count}`).join(" · ");
    const more = (p.carriers || []).length > 4 ? " …" : "";
    return `<tr>
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
function toggleBoard(){
  boardOpen = !boardOpen;
  $("#boardSection").classList.toggle("collapsed", !boardOpen);
  $("#boardToggle").setAttribute("aria-expanded", boardOpen ? "true" : "false");
  if (boardOpen) boardLoad();
}

/* ---- GUI events ---- */
$("#applyRange").addEventListener("click", load);
["startDate","endDate"].forEach(id => $("#"+id).addEventListener("keydown", e => { if (e.key === "Enter") load(); }));
$("#refresh").addEventListener("click", load);
$("#autoRefresh").addEventListener("change", () => armAuto());
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
