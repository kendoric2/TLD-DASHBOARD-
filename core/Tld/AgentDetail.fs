module Tld.AgentDetail

// One person's deals: every policy they closed as the agent and every one
// they enrolled as the fronter, with the SEP joined on, where their deals come
// from by state, and on request their call outcomes.
//
// Ported from the TLD dashboard's agent_detail, agent_dispo and _first_last.
// The requests are Tld.Queries.policyDetail, convertedLeads and agentCalls.

open System.Collections.Generic
open Tld.Rows

(*
 Policies say "Powers, Tony" and the call log says "Tony Powers", and a call
 log filter needs the exact string. "Last, First" becomes "First Last";
 anything without a comma is left alone.
*)
let firstLast (name: string) =
    let s = if isNull name then "" else name.Trim()
    match s.IndexOf(',') with
    | -1 -> s
    | i -> (s.Substring(i + 1).Trim() + " " + s.Substring(0, i).Trim()).Trim()

// One row per sale-stage policy, newest first, and everyone named on any of them
let detail (policyRows: Row array) (sepRows: Row array) =
    let sep = Dictionary<string, string>()
    for r in (if isNull sepRows then [||] else sepRows) |> Array.filter isObject do
        if rawText (get r "lead_id") <> "" then sep.[pyStr (get r "lead_id")] <- text r "sep"

    let deals = Policies.dedupeRows (if isNull policyRows then [||] else policyRows)
    let names = HashSet<string>()
    let rows =
        deals
        |> Array.map (fun r ->
            let agent, enroller = text r "agent_name", text r "fronter_name"
            if agent <> "" then names.Add agent |> ignore
            if enroller <> "" then names.Add enroller |> ignore
            let dateSold = rawText (get r "date_sold")
            {| date_sold = (if dateSold.Length > 10 then dateSold.Substring(0, 10) else dateSold)
               lead_id = get r "lead_id"
               agent = agent
               enroller = enroller // "" means the agent enrolled it themselves
               carrier = text r "carrier_name"
               plan = textOf (orElse (get r "product_name") (get r "product_plan_name"))
               sep = (match sep.TryGetValue(pyStr (get r "lead_id")) with | true, s -> s | _ -> "")
               state = (text r "lead_state").ToUpperInvariant()
               status = text r "status_name" |})
        |> List.ofArray
        |> List.sortWith (fun a b -> compare b.date_sold a.date_sold)
        |> Array.ofList
    rows, (names |> Array.ofSeq |> Array.sort)

let private noSummary = {| closed = 0; enrolled = 0; total = 0 |}

(*
 The view for one person. With nobody chosen it is just the list of people.
 A deal counts once, as closed when they were the agent, else as enrolled.
 States are split by role, since someone can close in one set and enroll in
 another.
*)
let person (policyRows: Row array) (sepRows: Row array) (agent: string) (rangeLabel: string) =
    let rows, people = detail policyRows sepRows
    if System.String.IsNullOrEmpty agent then
        box {| people = people; rows = [||]; summary = noSummary; range_label = rangeLabel; demo = false |}
    else
        let mine =
            rows
            |> Array.choose (fun r ->
                if r.agent = agent then Some {| r with role = "closed" |}
                elif r.enroller = agent then Some {| r with role = "enrolled" |}
                else None)
        let closed = mine |> Array.filter (fun r -> r.role = "closed") |> Array.length
        let order = ResizeArray<string>()
        let byState = Dictionary<string, int * int>()
        for r in mine do
            let st = if r.state = "" then "—" else r.state
            if not (byState.ContainsKey st) then
                order.Add st
                byState.[st] <- (0, 0)
            let c, e = byState.[st]
            byState.[st] <- if r.role = "closed" then (c + 1, e) else (c, e + 1)
        let states =
            order
            |> Seq.map (fun st -> let c, e = byState.[st] in {| state = st; closed = c; enrolled = e; total = c + e |})
            |> List.ofSeq
            |> List.sortWith (fun a b ->
                match compare b.total a.total with
                | 0 -> compare a.state b.state
                | c -> c)
            |> Array.ofList
        box
            {| people = people
               rows = mine
               agent = agent
               by_state = states
               summary = {| closed = closed; enrolled = mine.Length - closed; total = mine.Length |}
               range_label = rangeLabel
               demo = false |}

// The names to search the call log under, converted form first, as the Python tried them
let dispoNames (agent: string) =
    if System.String.IsNullOrEmpty agent then [||]
    else [| firstLast agent; agent |] |> Array.filter (fun n -> n <> "") |> Array.distinct

(*
 Call outcomes for one person. searched lists the names tried, so "no calls"
 can never be confused with a name that never matched. Automated dialling is
 logged under its own pseudo agent, so these are only calls they handled.
*)
let dispo (calls: Row array) (searched: string array) =
    if Array.isEmpty searched then
        {| dispositions = [||]; total = 0; searched = (null: string array) |}
    else
        let rows = (if isNull calls then [||] else calls) |> Array.filter isObject
        let order = ResizeArray<string>()
        let counts = Dictionary<string, int>()
        for r in rows do
            let k = Vendors.dispoLabel r
            if counts.ContainsKey k then counts.[k] <- counts.[k] + 1
            else
                order.Add k
                counts.[k] <- 1
        {| dispositions =
            order
            |> Seq.map (fun k -> {| status = k; count = counts.[k] |})
            |> List.ofSeq
            |> List.sortBy (fun d -> -d.count)
            |> Array.ofList
           total = rows.Length
           searched = searched |}
