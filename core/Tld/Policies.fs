module Tld.Policies

// What counts as a sale, and every count built from the policies TLD returns:
// Policies Sold, the carrier chart, active policies, states, agents,
// enrollments, recent sales and the sales board. Shared, so any report that
// counts policies counts the same ones the dashboard does.
//
// Ported from the TLD dashboard's tldcrm_client.py (_dedupe_key, _dedupe_rows,
// _kept_policies, _carrier_breakdown, _active_by_carrier, _state_breakdown,
// _agent_breakdown, _sales_board, enrollment_tracker, build_dashboard).
//
// Groups keep first-seen order and every sort is stable, because Python's are,
// and ties on the page were always broken by the order TLD returned the rows.

open System.Collections.Generic
open Tld.Rows

let private STAGES_COUNTED = set [ "sale" ] // drops "redacted" and trash so totals match TLD's carrier table
let EXCLUDED_CARRIERS = set [ "GTL" ]      // a separate product line, out of Policies Sold
let private NO_LABEL = "—"                 // the carrier or state shown when TLD left it blank

(*=======================================================
        ONE ROW PER REAL SALE
========================================================*)

// None, "", "0" and 0 are all "no id"
let private isEmptyId (value: obj) =
    isNull value
    || (match value with
        | :? string as s -> s = "" || s = "0"
        | :? float as f -> f = 0.0
        | _ -> false)

(*-------- This is critical --------*)
(*
 policy_id, else lead_id, always in that order. Any other *_id only becomes the
 key when a row has neither, so a row without a canonical id still dedupes
 instead of vanishing. Namespaced field:value so two id spaces never collide.
*)
let dedupeKey (row: Row) : string option =
    [ "policy_id"; "lead_id" ]
    |> List.tryPick (fun field ->
        let v = get row field
        if isEmptyId v then None else Some(field + ":" + string v))
    |> Option.orElse (
        keys row
        |> Array.sort
        |> Array.tryPick (fun field ->
            let v = get row field
            if (field = "id" || field.EndsWith "_id") && not (isEmptyId v) then Some(field + ":" + string v)
            else None))

(*-------- This is critical --------*)
(*
 Sale stage only, first row per key. Every count below starts from this, which
 is what keeps the carrier chart, Policies Sold, enrollments and the agent
 table adding up to each other. No carrier filter here: the chart needs GTL.
*)
let dedupeRows (rows: Row array) : Row array =
    let seen = HashSet<string>()
    rows
    |> Array.filter (fun row ->
        isObject row
        && STAGES_COUNTED.Contains((text row "stage").ToLowerInvariant())
        && (match dedupeKey row with
            | Some key -> seen.Add key
            | None -> false))

// Deduped and GTL excluded: the basis for Policies Sold and the enrollment tracker
let keptPolicies (deduped: Row array) : Row array =
    deduped |> Array.filter (fun row -> not (EXCLUDED_CARRIERS.Contains((text row "carrier_name").ToUpperInvariant())))

(*=======================================================
        GROUPING THAT KEEPS PYTHON'S ORDER
========================================================*)

// key -> accumulator, in first-seen order
let private groupInOrder (rows: Row array) (keyOf: Row -> string option) (seed: string -> 'acc) (add: 'acc -> Row -> 'acc) =
    let order = ResizeArray<string>()
    let acc = Dictionary<string, 'acc>()
    for row in rows do
        match keyOf row with
        | Some key ->
            if not (acc.ContainsKey key) then
                order.Add key
                acc.[key] <- seed key
            acc.[key] <- add acc.[key] row
        | None -> ()
    order |> Seq.map (fun key -> key, acc.[key]) |> List.ofSeq

// counts per label, high to low, ties in first-seen order
let private countBy (rows: Row array) (labelOf: Row -> string option) =
    groupInOrder rows labelOf (fun _ -> 0) (fun n _ -> n + 1) |> List.sortBy (fun (_, n) -> -n)

let private hasFronter (row: Row) =
    let id = text row "fronter_id"
    id <> "" && id <> "0"

let private orNoLabel (value: string) = if value = "" then NO_LABEL else value

(*=======================================================
        THE COUNTS
========================================================*)

// Every carrier including GTL, so the chart reconciles to TLD's own carrier table
let carrierBreakdown (deduped: Row array) =
    groupInOrder deduped (fun r -> Some(orNoLabel (text r "carrier_name"))) (fun _ -> 0, 0) (fun (count, enrolled) r ->
        count + 1, (if hasFronter r then enrolled + 1 else enrolled))
    |> List.sortBy (fun (_, (count, _)) -> -count)
    |> List.map (fun (label, (count, enrolled)) -> {| label = label; count = count; enrolled = enrolled |})
    |> Array.ofList

let private isActive (row: Row) = (text row "status_name").ToLowerInvariant() = "active"

// Sold and active per carrier (GTL included), with a per state split for the click through
let activeByCarrier (deduped: Row array) =
    groupInOrder deduped (fun r -> Some(orNoLabel (text r "carrier_name"))) (fun _ -> ResizeArray<Row>()) (fun list r ->
        list.Add r
        list)
    |> List.map (fun (carrier, rows) ->
        let rows = rows.ToArray()
        let states =
            groupInOrder
                rows
                (fun r ->
                    let state = (text r "lead_state").ToUpperInvariant()
                    if state = "" then None else Some state)
                (fun _ -> 0, 0)
                (fun (active, sold) r -> (if isActive r then active + 1 else active), sold + 1)
            |> List.sortBy (fun (_, (active, _)) -> -active)
            |> List.map (fun (state, (active, sold)) -> {| state = state; active = active; sold = sold |})
            |> Array.ofList
        {| carrier = carrier
           sold = rows.Length
           active = rows |> Array.filter isActive |> Array.length
           states = states |})
    |> List.sortBy (fun c -> -c.active)
    |> Array.ofList

// Deals per customer state (GTL excluded, so states add up to Policies Sold)
let stateBreakdown (kept: Row array) =
    groupInOrder
        kept
        (fun r ->
            let state = (text r "lead_state").ToUpperInvariant()
            if state = "" then None else Some state)
        (fun _ -> ResizeArray<Row>())
        (fun list r ->
            list.Add r
            list)
    |> List.map (fun (state, rows) ->
        let rows = rows.ToArray()
        {| state = state
           count = rows.Length
           enrolled = rows |> Array.filter hasFronter |> Array.length
           carriers =
            countBy rows (fun r -> Some(orNoLabel (text r "carrier_name")))
            |> List.map (fun (label, count) -> {| label = label; count = count |})
            |> Array.ofList
           agents =
            countBy rows (fun r ->
                let name = text r "agent_name"
                if name = "" then None else Some name)
            |> List.map (fun (name, count) -> {| name = name; count = count |})
            |> Array.ofList |})
    |> List.sortBy (fun s -> -s.count)
    |> Array.ofList

// Policies per agent (GTL excluded, so the table's total equals Policies Sold)
let agentBreakdown (kept: Row array) =
    countBy kept (fun r ->
        let name = text r "agent_name"
        if name = "" then None else Some name)
    |> List.map (fun (name, policies) -> {| name = name; policies = policies |})
    |> Array.ofList

(*
 Per enroller (fronter). A deal with no fronter was self generated and is
 counted under no_enroller rather than attributed to anyone. The name is the
 last non blank one TLD gave for that fronter id, as the Python kept it.
*)
let enrollmentTracker (kept: Row array) =
    let enrolled = kept |> Array.filter hasFronter
    let groups =
        groupInOrder enrolled (fun r -> Some(text r "fronter_id")) (fun _ -> (null: obj), ResizeArray<Row>()) (fun (name, list) r ->
            list.Add r
            orElse name (get r "fronter_name"), list)
        |> List.sortWith (fun (_, (nameA, a)) (_, (nameB, b)) ->
            match compare b.Count a.Count with
            | 0 -> compare (rawText nameA) (rawText nameB)
            | c -> c)
        |> List.map (fun (fronterId, (name, rows)) ->
            {| fronter_id = fronterId
               name = name
               count = rows.Count
               detail =
                countBy (rows.ToArray()) (fun r ->
                    Some(orNoLabel (text r "agent_name") + "\u0000" + orNoLabel (text r "carrier_name")))
                |> List.map (fun (key, count) ->
                    let parts = key.Split('\u0000')
                    {| agent = parts.[0]; carrier = parts.[1]; count = count |})
                |> Array.ofList |})
        |> Array.ofList
    {| total = groups |> Array.sumBy (fun g -> g.count)
       by_enroller = groups
       no_enroller = kept.Length - enrolled.Length |}

// Every sale in the range, newest first, from the same deduped rows as everything else
let recentSales (deduped: Row array) =
    deduped
    |> Array.map (fun r ->
        {| date_sold = get r "date_sold"
           lead_id = get r "lead_id"
           agent = text r "agent_name"
           agent_commission = num r "commission_paid"
           enroller = text r "fronter_name"
           fronter_commission = num r "commission_paid_fronter"
           carrier = text r "carrier_name" |})
    |> List.ofArray
    |> List.sortWith (fun a b -> compare (rawText b.date_sold) (rawText a.date_sold))
    |> Array.ofList

(*
 One row per person, agents and fronters together: deals closed as the agent,
 deals enrolled as the fronter, the commission on each, and the closed deals by
 carrier. Sorted by total, then closed, then name.
*)
let salesBoard (deduped: Row array) =
    let order = ResizeArray<string>()
    let people = Dictionary<string, int * int * float * ResizeArray<Row>>()
    let touch name =
        if not (people.ContainsKey name) then
            order.Add name
            people.[name] <- (0, 0, 0.0, ResizeArray<Row>())
    for r in deduped do
        let agent, fronter = text r "agent_name", text r "fronter_name"
        if agent <> "" then
            touch agent
            let closed, enrolled, commission, deals = people.[agent]
            deals.Add r
            people.[agent] <- (closed + 1, enrolled, commission + num r "commission_paid", deals)
        if fronter <> "" then
            touch fronter
            let closed, enrolled, commission, deals = people.[fronter]
            people.[fronter] <- (closed, enrolled + 1, commission + num r "commission_paid_fronter", deals)
    order
    |> Seq.map (fun name ->
        let closed, enrolled, commission, deals = people.[name]
        {| name = name
           closed = closed
           enrolled = enrolled
           total = closed + enrolled
           commission = round2 commission
           carriers =
            countBy (deals.ToArray()) (fun r -> Some(orNoLabel (text r "carrier_name")))
            |> List.map (fun (label, count) -> {| label = label; count = count |})
            |> Array.ofList |})
    |> List.ofSeq
    |> List.sortWith (fun a b ->
        match compare b.total a.total with
        | 0 ->
            match compare b.closed a.closed with
            | 0 -> compare a.name b.name
            | c -> c
        | c -> c)
    |> Array.ofList

let carriersIn (deduped: Row array) =
    deduped |> Array.map (fun r -> orNoLabel (text r "carrier_name")) |> Array.distinct |> Array.sort

(*=======================================================
        THE RESPONSES THE PAGE ALREADY EXPECTS
========================================================*)

type Range =
    abstract start: string
    abstract ``end``: string
    abstract label: string

(*
 The Dashboard tab, from one policies pull and one premium average. errors are
 the pulls that failed, already worded; the page shows them and still renders
 whatever did load, which is what the Python did.
*)
let dashboard (range: Range) (policyRows: Row array) (averagePremium: float) (errors: string array) =
    let deduped = dedupeRows (if isNull policyRows then [||] else policyRows)
    let kept = keptPolicies deduped
    {| demo = false
       range_label = range.label
       cached_at = (null: obj)
       date_range = {| start = range.start; ``end`` = range.``end`` |}
       kpis = {| policies_sold = kept.Length; avg_gtl_premium = averagePremium |}
       by_carrier = carrierBreakdown deduped
       active_by_carrier = activeByCarrier deduped
       by_state = stateBreakdown kept
       recent_sales = recentSales deduped
       agents = agentBreakdown kept
       enrollments = enrollmentTracker kept
       error = (if Array.isEmpty errors then null else "Some metrics didn't load: " + String.concat "; " errors) |}

// The sales board, optionally narrowed to one carrier; carriers always lists them all
let board (range: Range) (policyRows: Row array) (carrier: string) =
    let deduped = dedupeRows (if isNull policyRows then [||] else policyRows)
    let shown =
        if System.String.IsNullOrEmpty carrier then deduped
        else deduped |> Array.filter (fun r -> orNoLabel (text r "carrier_name") = carrier)
    {| board = salesBoard shown
       carriers = carriersIn deduped
       range_label = range.label
       date_range = {| start = range.start; ``end`` = range.``end`` |}
       demo = false |}
