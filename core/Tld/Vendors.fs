module Tld.Vendors

// The Vendors tab: who sells us leads, how many arrived, what they cost, every
// call we were billed for, and what happened on the calls.
//
// Ported from the TLD dashboard's vendor_catalogue, vendor_leads, vendor_cost,
// billed_calls, _dispo_day, dispo_breakdown and their helpers. The requests
// are in Tld.Queries.

open System.Collections.Generic
open Fable.Core.JsInterop
open Tld.Rows

let private BILLABLE_FLAGS = set [ "1"; "1.0"; "True"; "true" ] // how TLD has written "billable" on different days
let NOT_DISPOSITIONED = "Not dispositioned (no agent)"
let SPAM_KEY = "__filtered_spam__"

(*
 A billed call nobody handled: it reached us, we paid for it, no agent took
 it. Matched on the disposition text so a new TLD status of the same kind is
 caught too ("Inbound No Agent No Queue Drop", "Inbound After Hours Drop"...).
*)
let private UNHANDLED_MARKERS =
    [ "no agent"; "agent not available"; "queue timeout"; "after hours"; "queue drop"; "pre-routing drop" ]

(*
 Robocall traffic TLD's own filter intercepts. Not vendor traffic and never
 reaches an agent: on Sunday 2026-08-16 it was 96% of inbound, with caller id
 1111111111 alone 802 times. Counted as a disposition it made "no
 disposition" look like the biggest category, so it is set aside and reported.
*)
let private SPAM_DIDS = set [ "did system filter" ]

let private isBillable (value: obj) = BILLABLE_FLAGS.Contains(textOf value)

let isUnhandled (status: string) =
    let s = (if isNull status then "" else status).ToLowerInvariant()
    UNHANDLED_MARKERS |> List.exists s.Contains

(*
 A blank disposition is not missing data. It is a call that arrived and that
 no agent took, which is why it has no agent, no talk time and is never
 billable. Named, so it does not read as a bug. A few rows carry only a raw
 code with no name (WAITTO); those show the code.
*)
let dispoLabel (row: Row) =
    match text row "status_name", text row "status" with
    | "", "" -> NOT_DISPOSITIONED
    | "", code -> code
    | name, _ -> name

// key -> count, first seen order, then high to low with ties kept in that order
let private tally (labels: string seq) =
    let order = ResizeArray<string>()
    let counts = Dictionary<string, int>()
    for label in labels do
        if counts.ContainsKey label then counts.[label] <- counts.[label] + 1
        else
            order.Add label
            counts.[label] <- 1
    order |> Seq.map (fun k -> k, counts.[k]) |> List.ofSeq

(*=======================================================
        THE VENDOR LIST AND LEAD INTAKE
========================================================*)

// Every vendor, by name. Its status flag is unreliable (FALCON reads inactive at ~99% of volume)
let catalogue (rows: Row array) =
    rows
    |> Array.filter (fun r -> isObject r && textOf (get r "vendor_id") <> "")
    |> Array.map (fun r ->
        {| vendor_id = rawText (get r "vendor_id")
           name = text r "name"
           description = text r "description"
           price = num r "price"
           price_inbound = num r "price_inbound"
           status = text r "status_name" |})
    |> List.ofArray
    |> List.sortBy (fun v -> v.name.ToLowerInvariant())
    |> Array.ofList

(*
 Leads that arrived in the range, per vendor. The leads endpoint leaves
 vendor_name empty, so names come from the catalogue. billable means the lead
 cleared buffer time and was invoiced; $0 sources like INBOUND are re contacts
 of leads already owned, not purchases.
*)
let leads (rows: Row array) (vendors: obj array) =
    let names = Dictionary<string, string>()
    for v in (if isNull vendors then [||] else vendors) do
        names.[rawText (get v "vendor_id")] <- rawText (get v "name")
    let label (vid: string) =
        if vid = "" then "(none)"
        else
            match names.TryGetValue vid with
            | true, name when name <> "" -> name
            | _ -> "vendor " + vid
    let order = ResizeArray<string>()
    let acc = Dictionary<string, int * int * int>()
    for r in rows |> Array.filter isObject do
        let vid = rawText (get r "vendor_id")
        if not (acc.ContainsKey vid) then
            order.Add vid
            acc.[vid] <- (0, 0, 0)
        let n, billable, sold = acc.[vid]
        acc.[vid] <-
            (n + 1, (if isBillable (get r "billable") then billable + 1 else billable),
             (if num r "policies_sold" >= 1.0 then sold + 1 else sold))
    let byVendor =
        order
        |> Seq.map (fun vid ->
            let n, billable, sold = acc.[vid]
            {| vendor_id = vid; vendor = label vid; leads = n; billable = billable; sold = sold |})
        |> List.ofSeq
        |> List.sortBy (fun v -> -v.leads)
        |> Array.ofList
    {| by_vendor = byVendor
       totals =
        {| leads = byVendor |> Array.sumBy (fun v -> v.leads)
           billable = byVendor |> Array.sumBy (fun v -> v.billable)
           sold = byVendor |> Array.sumBy (fun v -> v.sold) |} |}

(*
 Every lead in the range by customer state AND by the vendor that sold it, so
 a weak state can be told apart from one vendor serving it badly. One pull,
 the same date_created basis as leads, so the two always agree on totals.
 Best converting state first; conversion is sold over billable, 0 with no
 billable leads so a lead starved state does not look perfect.
*)
let stateReport (rows: Row array) (vendors: obj array) =
    let names = Dictionary<string, string>()
    for v in (if isNull vendors then [||] else vendors) do
        names.[rawText (get v "vendor_id")] <- rawText (get v "name")
    let vendorName (vid: string) =
        match names.TryGetValue vid with
        | true, n when n <> "" -> n
        | _ -> if vid = "" then "(none)" else "vendor " + vid
    let conv (billable: int) (sold: int) = if billable > 0 then pyRound 1 (float sold / float billable * 100.0) else 0.0

    let stateOrder = ResizeArray<string>()
    let states = Dictionary<string, int * int * int * ResizeArray<string> * Dictionary<string, int * int * int>>()
    for r in rows |> Array.filter isObject do
        let state = (text r "state").ToUpperInvariant()
        if state <> "" then
            let vname = vendorName (rawText (get r "vendor_id"))
            let b = if isBillable (get r "billable") then 1 else 0
            let s = if num r "policies_sold" >= 1.0 then 1 else 0
            if not (states.ContainsKey state) then
                stateOrder.Add state
                states.[state] <- (0, 0, 0, ResizeArray(), Dictionary())
            let leads, billable, sold, vorder, vs = states.[state]
            if not (vs.ContainsKey vname) then
                vorder.Add vname
                vs.[vname] <- (0, 0, 0)
            let vl, vb, vsold = vs.[vname]
            vs.[vname] <- (vl + 1, vb + b, vsold + s)
            states.[state] <- (leads + 1, billable + b, sold + s, vorder, vs)

    let byState =
        stateOrder
        |> Seq.map (fun state ->
            let leads, billable, sold, vorder, vs = states.[state]
            {| state = state
               leads = leads
               billable = billable
               sold = sold
               conversion = conv billable sold
               vendors =
                vorder
                |> Seq.map (fun v ->
                    let l, b, s = vs.[v]
                    {| vendor = v; leads = l; billable = b; sold = s; conversion = conv b s |})
                |> List.ofSeq
                |> List.sortBy (fun v -> -v.sold)
                |> Array.ofList |})
        |> List.ofSeq
        |> List.sortWith (fun a b ->
            match compare b.conversion a.conversion with
            | 0 -> compare b.billable a.billable
            | c -> c)
        |> Array.ofList
    {| by_state = byState
       totals =
        {| leads = byState |> Array.sumBy (fun s -> s.leads)
           billable = byState |> Array.sumBy (fun s -> s.billable)
           sold = byState |> Array.sumBy (fun s -> s.sold) |} |}

(*
 The vendor export's Sold Policies sheet: every sale stage policy on the leads
 created in the range that produced one, the same leads the Sold column
 counts, with its date sold and the lead's phone. One row per policy, oldest
 sale first. leadsWithPhone is Tld.Queries.leadsCreatedWithPhone's answer.
*)
let soldLeadIds (leadsWithPhone: Row array) =
    leadsWithPhone
    |> Array.filter (fun r -> isObject r && textOf (get r "lead_id") <> "" && num r "policies_sold" >= 1.0)
    |> Array.map (fun r -> textOf (get r "lead_id"))
    |> Array.distinct
    |> Array.sort

let soldPolicies (leadsWithPhone: Row array) (policyRows: Row array) =
    let phoneOf = Dictionary<string, string>()
    for r in leadsWithPhone |> Array.filter isObject do
        let id = textOf (get r "lead_id")
        if id <> "" && num r "policies_sold" >= 1.0 then phoneOf.[id] <- text r "phone"
    Policies.dedupeRows (if isNull policyRows then [||] else policyRows)
    |> Array.choose (fun p ->
        match phoneOf.TryGetValue(textOf (get p "lead_id")) with
        | true, phone ->
            let sold = rawText (get p "date_sold")
            Some {| date_sold = (if sold.Length > 10 then sold.Substring(0, 10) else sold); phone = phone |}
        | _ -> None)
    |> List.ofArray
    |> List.sortBy (fun r -> r.date_sold)
    |> Array.ofList

(*=======================================================
        COST
========================================================*)

// Spend, sales, billable calls, CPA and conversion for one vendor or all, from the report's totals
let cost (payload: obj) =
    let resp = unwrapResults payload
    let totals = if isObject resp && isObject (get resp "totals") then get resp "totals" else null
    let spend, sales, calls = num totals "costs_all", num totals "sales", num totals "calls_billable"
    {| spend = spend
       sales = sales
       calls_billable = calls
       cpa = (if sales <> 0.0 then round2 (spend / sales) else 0.0)
       conversion = (if calls <> 0.0 then pyRound 1 (sales / calls * 100.0) else 0.0) |}

(*=======================================================
        BILLED CALLS
========================================================*)

(*-------- This is critical --------*)
(*
 Every call we were billed for, the audit trail behind an invoice; reconciled
 to the cent against TLD's billing report (438 calls, $17,520 on 2026-08-18).

 A billed call is never itself "Sale Made": billing is on the inbound leg when
 it clears buffer time, and the sale lands on a later leg after transfer, so
 the two sets never intersect. A sale is attributed through the LEAD instead,
 and counted per distinct lead, so someone who rings twice and buys once is
 one sale and conversions can never exceed policies actually sold.

 lead_vendor_lead_code is the CRM's lead id. The call log's own lead_id is the
 dialer's (7 digits against the CRM's 9) and matches nothing.
*)
let billed (rows: Row array) (policyRows: Row array) =
    let calls =
        rows
        |> Array.filter (fun r -> isObject r && isBillable (get r "billable"))
        |> Array.map (fun r ->
            {| call_date = rawText (get r "call_date")
               vendor = text r "vendor_description"
               agent = text r "agent_name"
               status = text r "status_name"
               lead_id = orElse (box "") (get r "lead_vendor_lead_code")
               dialer_lead_id = get r "lead_id"
               talk_sec = num r "sec_talk"
               duration = rawText (get r "duration_call")
               cost = num r "cost" |})
        |> List.ofArray
        |> List.sortWith (fun a b -> compare b.call_date a.call_date)
        |> Array.ofList

    let soldLeads = HashSet<string>()
    for p in Policies.dedupeRows (if isNull policyRows then [||] else policyRows) do
        let id = textOf (get p "lead_id")
        if id <> "" then soldLeads.Add id |> ignore

    let rows =
        calls
        |> Array.map (fun c ->
            let converted = textOf c.lead_id <> "" && soldLeads.Contains(textOf c.lead_id)
            {| c with converted = converted |})
    let spend = rows |> Array.sumBy (fun r -> r.cost)
    let sales = rows |> Array.filter (fun r -> r.converted) |> Array.map (fun r -> textOf r.lead_id) |> Array.distinct
    let dropped = rows |> Array.filter (fun r -> isUnhandled r.status)
    let byStatus =
        let order = ResizeArray<string>()
        let acc = Dictionary<string, int * float>()
        for r in rows do
            let s = if r.status = "" then "(blank)" else r.status
            if not (acc.ContainsKey s) then
                order.Add s
                acc.[s] <- (0, 0.0)
            let n, c = acc.[s]
            acc.[s] <- (n + 1, c + r.cost)
        order
        |> Seq.map (fun s -> let n, c = acc.[s] in {| status = s; calls = n; cost = c |})
        |> List.ofSeq
        |> List.sortBy (fun s -> -s.calls)
        |> Array.ofList

    {| rows = rows
       summary =
        {| calls = rows.Length
           spend = round2 spend
           sales = sales.Length
           converted_calls = rows |> Array.filter (fun r -> r.converted) |> Array.length
           unlinked = rows |> Array.filter (fun r -> textOf r.lead_id = "") |> Array.length
           cost_per_sale = (if sales.Length > 0 then round2 (spend / float sales.Length) else 0.0)
           dropped = dropped.Length
           dropped_cost = round2 (dropped |> Array.sumBy (fun r -> r.cost))
           dropped_pct = (if rows.Length > 0 then pyRound 1 (float dropped.Length / float rows.Length * 100.0) else 0.0) |}
       by_status = byStatus
       unhandled_statuses = dropped |> Array.map (fun r -> r.status) |> Array.distinct |> Array.sort |}

(*=======================================================
        DISPOSITIONS, ONE DAY AT A TIME
========================================================*)

(*
 One day's calls as { disposition: count }, with the filtered robocalls under
 SPAM_KEY so the page can say what was removed. A plain object, because the
 shell keeps finished days and hands them back here: a finished call's outcome
 never changes, and at ~33k calls a day a month would otherwise be a million
 rows on every view.
*)
let dayCounts (rows: Row array) =
    let calls = rows |> Array.filter isObject
    let spam = calls |> Array.filter (fun r -> SPAM_DIDS.Contains((text r "did_description").ToLowerInvariant())) |> Array.length
    let counts =
        calls
        |> Array.filter (fun r -> not (SPAM_DIDS.Contains((text r "did_description").ToLowerInvariant())))
        |> Array.map dispoLabel
        |> tally
    createObj ((counts |> List.map (fun (k, n) -> k, box n)) @ (if spam > 0 then [ SPAM_KEY, box spam ] else []))

// The day by day total disagrees with TLD's own count, so the kept days are wrong and must be rebuilt
let disagrees (ours: float) (theirs: float) =
    theirs <> 0.0 && abs (ours - theirs) > max 2.0 (theirs * 0.01)

// Sum of a day's counts, spam included, as the Python compared it
let dayTotal (counts: obj) = keys counts |> Array.sumBy (fun k -> num counts k)

(*
 The days added up in date order. Ties between dispositions with the same
 count fall in that order; the Python added days as they finished, so its
 order between equal counts was never fixed.
*)
let breakdown (days: obj array) (reportedTotal: float) (cachedDays: int) =
    let order = ResizeArray<string>()
    let totals = Dictionary<string, float>()
    for day in days do
        if not (isNull day) then
            for k in keys day do
                if not (totals.ContainsKey k) then
                    order.Add k
                    totals.[k] <- 0.0
                totals.[k] <- totals.[k] + num day k
    let spam = if totals.ContainsKey SPAM_KEY then totals.[SPAM_KEY] else 0.0
    let rows =
        order
        |> Seq.filter (fun k -> k <> SPAM_KEY)
        |> Seq.map (fun k -> {| status = k; count = totals.[k] |})
        |> List.ofSeq
        |> List.sortBy (fun r -> -r.count)
        |> Array.ofList
    {| dispositions = rows
       total = rows |> Array.sumBy (fun r -> r.count)
       reported_total = reportedTotal
       filtered_spam = spam
       days = days.Length
       cached_days = cachedDays |}
