module Tld.Cpa

// TLD's cost report read into what the pages show: cost and CPA per agent, and
// the period's Total Spend, Blended CPA, Billable Calls and Conversion Rate.
//
// Ported from the TLD dashboard's _fetch_agent_cpa, _name_keys and
// _cpa_has_data. The request is Tld.Queries.costReport.

open System.Collections.Generic
open Fable.Core.JsInterop
open Tld.Rows

(*
 Two keys per agent so the cost report and the policies line up. The report
 names people "First Last" and policies "Last, First", and some carry a middle
 name or initial in one and not the other.

   full   every word, first name first     "Willis, Jarvis" -> "jarvis willis"
   loose  first and last word only          "Andrew M Giesse" -> "andrew giesse"
*)
let nameKeys (name: string) =
    let s = (if isNull name then "" else name).Trim().ToLowerInvariant()
    let s =
        match s.IndexOf(',') with
        | -1 -> s
        | i -> s.Substring(i + 1).Trim() + " " + s.Substring(0, i).Trim()
    let words = s.Split([| ' '; '\t'; '\n'; '\r' |]) |> Array.filter (fun w -> w <> "")
    let full = String.concat " " words
    let loose = if words.Length >= 2 then words.[0] + " " + words.[words.Length - 1] else full
    full, loose

let private listIn (container: obj) =
    [ "results"; "data"; "rows"; "report"; "records"; "agents" ]
    |> List.tryPick (fun key ->
        let v = get container key
        if isArray v then Some(unbox<Row array> v) else None)

(*-------- This is critical --------*)
(*
 The report answers as { records: [...], totals: {...} } once unwrapped. Its
 own totals row wins, because it is what TLD's screen shows; only when it is
 missing are the rows summed. Conversion is sales over billable CALLS, every
 vendor, the CRM's "Sales / All Calls %". Billable leads made it read about 5
 points high, which is why the word calls is in capitals.
*)
let report (payload: obj) =
    let resp = unwrapResults payload
    let rows, totals =
        if isObject resp then
            (listIn resp |> Option.defaultValue [||]), (if isObject (get resp "totals") then get resp "totals" else null)
        elif isNull resp then [||], null
        else unbox<Row array> resp, null
    let rows = rows |> Array.filter isObject

    // full name first, then the loose alias only where nothing claimed it yet
    let order = ResizeArray<string>()
    let byAgent = Dictionary<string, obj>()
    let put key value =
        if not (byAgent.ContainsKey key) then order.Add key
        byAgent.[key] <- value
    for row in rows do
        let full, loose = nameKeys (rawText (get row "agent"))
        if full <> "" then
            let record = box {| cpa = num row "cpa_cost_calls_all_by_sales"; cost = num row "costs_all" |}
            put full record
            if not (byAgent.ContainsKey loose) then put loose record

    let hasTotals = not (isNull totals) && keys totals |> Array.isEmpty |> not
    let cost, sales, cpa, calls =
        if hasTotals then
            num totals "costs_all", num totals "sales", num totals "cpa_cost_calls_all_by_sales", num totals "calls_billable"
        else
            let sum key = rows |> Array.sumBy (fun r -> num r key)
            let c, s = sum "costs_all", sum "sales"
            c, s, (if s <> 0.0 then pyRound 2 (c / s) else 0.0), sum "calls_billable"

    {| by_agent = createObj (order |> Seq.map (fun key -> key, byAgent.[key]))
       totals =
        {| cost = cost
           sales = sales
           cpa = cpa
           billable_calls = calls
           conversion = (if calls <> 0.0 then pyRound 1 (sales / calls * 100.0) else 0.0) |} |}

// An empty result is never cached: zeros held for minutes read as a real day with no sales
let hasData (result: obj) =
    let byAgent = get result "by_agent"
    let totals = get result "totals"
    (isObject byAgent && not (Array.isEmpty (keys byAgent)))
    || (isObject totals && [ "cost"; "sales"; "billable_calls" ] |> List.exists (fun k -> num totals k <> 0.0))

// The answer the page gets when the report could not be fetched, with the reason
let failed (message: string) = {| by_agent = createObj []; totals = createObj []; error = message |}
