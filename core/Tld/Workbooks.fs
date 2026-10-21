module Tld.Workbooks

// What goes in each of the TLD dashboard's Excel exports: sheets of plain
// cells, the file name, nothing about how Excel is written. The shell turns a
// workbook from here into a file with exceljs (lib/tld/workbook.js).
//
// Ported from the TLD dashboard's export_xlsx.py. Plain cells only, as the
// Python wrote them: no fonts, fills or formats, except the Sold Policies
// sheet's phone column kept as text so Excel shows every digit.

open System
open Fable.Core.JsInterop
open Tld.Rows

(*
 A sheet: its tab name and its rows, top to bottom, each a list of cells
 (text, a number, or null for empty). An empty row is an empty list, as
 openpyxl's ws.append([]) left one. textColumn, when set, is a 1 based column
 kept as text from fromRow down; widths are column widths left to right.
*)
type Sheet =
    { name: string
      rows: obj array array
      textColumn: int
      fromRow: int
      widths: float array }

let private sheet (name: string) (rows: obj list list) =
    { name = name; rows = rows |> List.map Array.ofList |> Array.ofList; textColumn = 0; fromRow = 0; widths = [||] }

let private book (filename: string) (sheets: Sheet list) = {| filename = filename; sheets = Array.ofList sheets |}

let private s (text: string) = box text
let private n (value: float) = box value
let private i (value: int) = box value

(*=======================================================
        TEXT AS PYTHON FORMATTED IT
========================================================*)

// Python's f"{n:,}" for the whole numbers these reports print
let commas (value: float) =
    let negative = value < 0.0
    let digits = (abs (Math.Round value)).ToString("0")
    let grouped =
        digits
        |> Seq.rev
        |> Seq.chunkBySize 3
        |> Seq.map (fun c -> String(Array.rev c))
        |> Seq.rev
        |> String.concat ","
    (if negative then "-" else "") + grouped

// Python's f"${n:,.2f}"
let money (value: float) =
    let fixed' = (abs value).ToString("0.00")
    let whole, cents = fixed'.Substring(0, fixed'.Length - 3), fixed'.Substring(fixed'.Length - 2)
    (if value < 0.0 then "-" else "") + "$" + commas (float whole) + "." + cents

// 'Powers, Tony' -> 'Powers-Tony', so file names stay clean
let safeName (value: string) =
    let raw = (if isNull value then "" else value).Trim()
    let dashed = String(raw.ToCharArray() |> Array.map (fun c -> if Char.IsLetterOrDigit c then c else '-'))
    let mutable out = dashed
    while out.Contains "--" do
        out <- out.Replace("--", "-")
    match out.Trim('-') with
    | "" -> "agent"
    | name -> name

// Excel tab names: at most 31 characters, and none of []:*?/\
let sheetTitle (value: string) =
    let cleaned = String((if isNull value then "" else value).ToCharArray() |> Array.map (fun c -> if "[]:*?/\\".Contains c then ' ' else c)).Trim()
    if cleaned = "" then "Agent Detail" elif cleaned.Length > 31 then cleaned.Substring(0, 31) else cleaned

// A share as Python's round(part / whole * 100, 1), 0 when the whole is 0
let private share (part: float) (whole: float) = if whole <> 0.0 then pyRound 1 (part / whole * 100.0) else 0.0

// Lead ids go in as numbers so Excel sorts them; anything not a whole number stays text
let private asNumberIfInt (value: obj) =
    let trimmed = (rawText value).Trim()
    if trimmed <> "" && trimmed |> Seq.forall Char.IsDigit then n (float trimmed)
    elif isNull value then s ""
    else value

let private orEmpty (value: obj) = if isNull value then s "" else value

(*=======================================================
        THE DASHBOARD TAB
========================================================*)

// Active vs sold per carrier, of what was sold in the range: the on screen table
let active (start: string) (finish: string) (label: string) (rows: obj array) =
    let carriers =
        rows |> Array.map (fun r -> rawText (get r "carrier"), num r "active", num r "sold") |> List.ofArray
    let totalActive, totalSold = carriers |> List.sumBy (fun (_, a, _) -> a), carriers |> List.sumBy (fun (_, _, b) -> b)
    let body = carriers |> List.map (fun (c, a, b) -> [ s c; n a; n b; n (share a b) ])
    let total = if carriers.IsEmpty then [] else [ []; [ s "TOTAL"; n totalActive; n totalSold; n (share totalActive totalSold) ] ]
    book
        (sprintf "ActivePolicies_%s_%s.xlsx" start finish)
        [ sheet
              "Active Policies"
              ([ [ s ("Active Policies — " + label) ]
                 [ s (sprintf "Range: %s to %s" start finish) ]
                 [ s "In force, of what was sold in this range" ]
                 []
                 [ s "Carrier"; s "Active"; s "Sold"; s "% Active" ] ]
               @ body
               @ total) ]

// Deals by customer state and carrier (GTL excluded), and with agents, by agent on a second sheet
let byState (start: string) (finish: string) (label: string) (rows: obj array) (includeAgents: bool) =
    let lines (listKey: string) (nameKey: string) =
        rows
        |> Array.collect (fun st ->
            let total = num st "count"
            let items = get st listKey
            (if isNull items then [||] else unbox<obj array> items)
            |> Array.map (fun c -> [ s (rawText (get st "state")); s (rawText (get c nameKey)); n (num c "count"); n total; n (share (num c "count") total) ]))
        |> List.ofArray
    let carriers =
        sheet
            "By Carrier"
            ([ [ s ("Production by State — " + label) ]
               [ s (sprintf "Range: %s to %s" start finish) ]
               [ s "Deals by customer state, broken down by carrier (GTL excluded)" ]
               []
               [ s "State"; s "Carrier"; s "Deals"; s "State Total"; s "Share of State" ] ]
             @ lines "carriers" "label")
    let agents =
        sheet
            "By Agent"
            ([ [ s (sprintf "Production by State — %s (by agent)" label) ]
               [ s (sprintf "Range: %s to %s" start finish) ]
               []
               [ s "State"; s "Agent"; s "Deals"; s "State Total"; s "Share of State" ] ]
             @ lines "agents" "name")
    book
        (sprintf "ProductionByState_%s_%s%s.xlsx" start finish (if includeAgents then "_with_agents" else ""))
        (if includeAgents then [ carriers; agents ] else [ carriers ])

(*=======================================================
        AGENT DETAIL
========================================================*)

let private DETAIL_COLUMNS =
    [ "Date Sold", "date_sold"; "Lead ID", "lead_id"; "Role", "role"; "Agent", "agent"; "Enroller", "enroller"
      "State", "state"; "Carrier", "carrier"; "Plan", "plan"; "SEP", "sep" ]

(*
 The on screen order: the sorted column, blanks last whichever direction.
 Lead ids sort as numbers, everything else as lower case text.
*)
let sortRows (rows: obj array) (key: string) (descending: bool) =
    let key = if DETAIL_COLUMNS |> List.exists (fun (_, k) -> k = key) then key else "date_sold"
    let filled, blank = rows |> Array.partition (fun r -> (rawText (get r key)).Trim() <> "")
    let sorted =
        filled
        |> List.ofArray
        |> List.sortWith (fun a b ->
            let c =
                if key = "lead_id" then compare (numOf (get a key)) (numOf (get b key))
                else compare ((rawText (get a key)).ToLowerInvariant()) ((rawText (get b key)).ToLowerInvariant())
            if descending then -c else c)
    Array.append (Array.ofList sorted) blank

let agentDetail (agent: string) (start: string) (finish: string) (rows: obj array) =
    book
        (sprintf "AgentDetail_%s_%s_%s.xlsx" (safeName agent) start finish)
        [ sheet
              (sheetTitle agent)
              ([ [ s ("Agent: " + agent) ]; [ s (sprintf "Range: %s to %s" start finish) ]; []
                 DETAIL_COLUMNS |> List.map (fst >> s) ]
               @ (rows
                  |> List.ofArray
                  |> List.map (fun r ->
                      DETAIL_COLUMNS |> List.map (fun (_, k) -> if k = "lead_id" then asNumberIfInt (get r k) else orEmpty (get r k))))) ]

(*
 Call outcomes as a plain sheet: what it covers, then Disposition, Count and
 Share. The notes (range, direction, robocalls excluded) are what make a share
 column readable six months later.
*)
let dispositions (title: string) (notes: string array) (rows: obj array) (total: float) (tabName: string) (filename: string) =
    let body = rows |> List.ofArray |> List.map (fun r -> [ s (rawText (get r "status")); n (num r "count"); n (share (num r "count") total) ])
    book
        filename
        [ sheet
              (sheetTitle tabName)
              ([ [ s title ] ]
               @ (notes |> List.ofArray |> List.map (fun note -> [ s note ]))
               @ [ []; [ s "Disposition"; s "Count"; s "Share" ] ]
               @ body
               @ (if rows.Length > 0 then [ []; [ s "TOTAL"; n total; n (if total <> 0.0 then 100.0 else 0.0) ] ] else [])) ]

(*=======================================================
        VENDORS
========================================================*)

// The vendors table as on screen, and a Sold Policies sheet behind its Sold column
let vendors (start: string) (finish: string) (label: string) (rows: obj array) (totals: obj) (sold: obj array) =
    let tLeads, tBillable, tSold = num totals "leads", num totals "billable", num totals "sold"
    let body =
        rows
        |> List.ofArray
        |> List.map (fun r ->
            let price = num r "price"
            [ s (rawText (get r "vendor")); n (num r "leads"); n (num r "billable"); n (num r "sold")
              n (share (num r "sold") (num r "billable")); (if price <> 0.0 then n (pyRound 2 price) else s ""); s (rawText (get r "status")) ])
    let main =
        sheet
            (sheetTitle (if String.IsNullOrEmpty label then "Vendors" else label))
            ([ [ s ("Vendors: " + (if String.IsNullOrEmpty label then "all vendors" else label)) ]
               [ s (sprintf "Range: %s to %s" start finish) ]
               [ s (sprintf "%s leads  ·  %s billable  ·  %s produced a policy" (commas tLeads) (commas tBillable) (commas tSold)) ]
               []
               [ s "Vendor"; s "Leads"; s "Billable"; s "Sold"; s "Sold / Billable"; s "Price"; s "Status" ] ]
             @ body
             @ (if rows.Length > 0 then [ []; [ s "TOTAL"; n tLeads; n tBillable; n tSold; n (share tSold tBillable); s ""; s "" ] ] else []))
    let soldSheet =
        { sheet
              "Sold Policies"
              ([ [ s (sprintf "Sold policies: %s, leads created %s to %s" (if String.IsNullOrEmpty label then "all vendors" else label) start finish) ]
                 [ s (sprintf "%s policies on the %s leads that produced one" (commas (float sold.Length)) (commas tSold)) ]
                 []
                 [ s "Date Sold"; s "Phone Number" ] ]
               @ (sold |> List.ofArray |> List.map (fun r -> [ s (rawText (get r "date_sold")); s (rawText (get r "phone")) ]))) with
            textColumn = 2
            fromRow = 5
            widths = [| 14.0; 16.0 |] }
    book (sprintf "Vendors_%s_%s_%s.xlsx" (safeName (if String.IsNullOrEmpty label then "all" else label)) start finish) [ main; soldSheet ]

// Best and worst states, and which vendor is behind each, from one pull
let stateReport (start: string) (finish: string) (data: obj) =
    let states = get data "by_state" |> fun v -> if isNull v then [||] else unbox<obj array> v
    let totals = get data "totals"
    let leads, billable, sold = num totals "leads", num totals "billable", num totals "sold"
    let ranked =
        sheet
            "Best-Worst States"
            ([ [ s (sprintf "State performance — %s to %s" start finish) ]
               [ s "Ranked by conversion (sold ÷ billable leads), best first. Watch the Billable column — a handful of leads can swing a percentage." ]
               [ s (sprintf "%s leads  ·  %s billable  ·  %s sold" (commas leads) (commas billable) (commas sold)) ]
               []
               [ s "State"; s "Leads"; s "Billable"; s "Sold"; s "Conversion" ] ]
             @ (states |> List.ofArray |> List.map (fun st -> [ s (rawText (get st "state")); n (num st "leads"); n (num st "billable"); n (num st "sold"); n (num st "conversion") ]))
             @ (if states.Length > 0 then [ []; [ s "TOTAL"; n leads; n billable; n sold; n (share sold billable) ] ] else []))
    let split =
        sheet
            "By State x Vendor"
            ([ [ s (sprintf "State × vendor breakdown — %s to %s" start finish) ]
               [ s "Same states, split by which vendor sold the lead. Grouped by state, highest-selling vendor first within each." ]
               []
               [ s "State"; s "State Conversion"; s "Vendor"; s "Leads"; s "Billable"; s "Sold"; s "Conversion" ] ]
             @ (states
                |> List.ofArray
                |> List.collect (fun st ->
                    (get st "vendors" |> fun v -> if isNull v then [||] else unbox<obj array> v)
                    |> List.ofArray
                    |> List.map (fun v ->
                        [ s (rawText (get st "state")); n (num st "conversion"); s (rawText (get v "vendor")); n (num v "leads")
                          n (num v "billable"); n (num v "sold"); n (num v "conversion") ]))))
    book (sprintf "StatePerformance_%s_%s.xlsx" start finish) [ ranked; split ]

let private BILLED_COLUMNS =
    [ "Call Time", "call_date"; "Vendor", "vendor"; "Agent", "agent"; "Disposition", "status"; "Talk (sec)", "talk_sec"
      "Cost", "cost"; "Lead ID", "lead_id"; "Dialer ID", "dialer_lead_id" ]

// The calls billed in a range, one per row, to check against a vendor's invoice
let billed (start: string) (finish: string) (label: string) (summary: obj) (rows: obj array) =
    let name = if String.IsNullOrEmpty label then "all vendors" else label
    let cell (r: obj) (key: string) =
        let v = get r key
        match key with
        | "cost" | "talk_sec" when (rawText v).Trim() <> "" -> n (numOf v)
        | "lead_id" | "dialer_lead_id" -> asNumberIfInt v
        | _ -> orEmpty v
    book
        (sprintf "BilledCalls_%s_%s_%s.xlsx" (safeName (if String.IsNullOrEmpty label then "all" else label)) start finish)
        [ sheet
              (sheetTitle (if String.IsNullOrEmpty label then "Billed Calls" else label))
              ([ [ s ("Billed calls: " + name) ]
                 [ s (sprintf "Range: %s to %s" start finish) ]
                 [ s (sprintf "%s calls  ·  %s total  ·  %s sales  ·  %s unanswered (%s)"
                          (string (int (num summary "calls"))) (money (num summary "spend")) (string (int (num summary "sales")))
                          (string (int (num summary "dropped"))) (money (num summary "dropped_cost"))) ]
                 []
                 BILLED_COLUMNS |> List.map (fst >> s) ]
               @ (rows |> List.ofArray |> List.map (fun r -> BILLED_COLUMNS |> List.map (fun (_, k) -> cell r k)))) ]

(*=======================================================
        TRANSFER CHECK
========================================================*)

let private REP_COLUMNS =
    [ "Fronter", "rep"; "Transfers", "transfers"; "Found in TLD", "found"; "Paid Sales", "payable"
      "Verified Policies", "policies"; "· Manhattan Life", "pol_manhattan"; "· MAPD", "pol_mapd"
      "Awaiting Verification", "awaiting"; "Pending (Sale Made, no policy yet)", "pending"
      "Later Day (not paid)", "later_day"; "Not Found", "not_found" ]

let private TRANSFER_COLUMNS =
    [ "Fronter", "rep"; "Campaign", "campaign"; "Product Line", "product_line"; "Transfer Time", "transfer_time"
      "Phone (last 4)", "phone_last4"; "Lead ID", "lead_id"; "Result", "result"; "Agent", "agent"
      "Disposition", "disposition"; "Carrier", "carrier"; "Policy Status", "policy_status"; "Verified By", "verified_by"
      "Date Sold", "date_sold"; "Landed Vendor", "landed_vendor"; "Line", "line"; "TLD Call Time", "call_time" ]

(*
 For payroll: a per fronter summary with the pay week, the warning when
 transfers outside the week already sold, and the rules in words; then every
 transfer as the backup.
*)
let transfers (data: obj) =
    let range, fileRange, totals = get data "range", get data "file_range", get data "totals"
    let rows key = get data key |> fun v -> if isNull v then [||] else unbox<obj array> v
    let header =
        let line = sprintf "Transfers: %s to %s  ·  checked %s" (rawText (get range "start")) (rawText (get range "end")) (rawText (get data "checked_at"))
        let dropped = num data "dropped"
        if dropped <> 0.0 then
            line + sprintf "  ·  %s row(s) outside this pay week were ignored (file covers %s to %s)" (string (int dropped)) (rawText (get fileRange "start")) (rawText (get fileRange "end"))
        else line
    let warning =
        let ds = get data "dropped_sales"
        if isNull ds || num ds "transfers" = 0.0 then []
        else
            let part (key: string) (todo: string) =
                let g = get ds key
                if isNull g then None
                else
                    let first, last = rawText (get g "first"), rawText (get g "last")
                    let span = if first = last then first else first + " to " + last
                    Some(sprintf "%s transferred %s this week (%s) — %s" (string (int (num g "transfers"))) key span todo)
            let parts =
                [ part "before" "make sure last week's check included them"; part "after" "include them in next week's check" ]
                |> List.choose id
            [ [ s (sprintf "WARNING: %s ignored transfer(s) already have a sale: %s." (string (int (num ds "transfers"))) (String.concat "; " parts)) ] ]
    let payOnce = match get data "pay_once" with :? bool as b -> b | _ -> false
    let summary =
        sheet
            "Payroll Summary"
            ([ [ s "Fronter Transfer Check — DialedIN transfers matched to TLD" ]; [ s header ] ]
             @ warning
             @ [ [ s ("Paid = a new policy created after the transfer and on the same day, verified by a manager. Callbacks and a different enrolling agent still count. "
                      + (if payOnce then "Paid once per transfer." else "Paid per new policy.")
                      + " Later Day = sold, but on a later day than the transfer, so not paid."
                      + " Pending = agent marked Sale Made but no policy entered yet.") ]
                 []
                 REP_COLUMNS |> List.map (fst >> s) ]
             @ (rows "by_rep" |> List.ofArray |> List.map (fun r -> REP_COLUMNS |> List.map (fun (_, k) -> orEmpty (get r k))))
             @ [ []; s "TOTAL" :: (REP_COLUMNS |> List.tail |> List.map (fun (_, k) -> n (num totals k))) ]
             @ (let lines = rows "by_line"
                if lines.Length = 0 then []
                else
                    [ []
                      [ s "By product line — a sale is counted under its CARRIER's line, not the campaign the fronter was dialing (the two disagree). Reporting only: the fronter is paid for whatever their transfer sold." ]
                      [ s "Product Line"; s "Transfers"; s "Paid Sales"; s "Verified Policies"; s "Awaiting Verification"; s "Pending"; s "Later Day (not paid)"; s "Not Found" ] ]
                    @ (lines
                       |> List.ofArray
                       |> List.map (fun g ->
                           [ s (rawText (get g "line")); n (num g "transfers"); n (num g "paid"); n (num g "policies"); n (num g "awaiting")
                             n (num g "pending"); n (num g "later_day"); n (num g "not_found") ]))))
    let detail =
        sheet
            "Transfer Detail"
            ([ TRANSFER_COLUMNS |> List.map (fst >> s) ]
             @ (rows "rows" |> List.ofArray |> List.map (fun r -> TRANSFER_COLUMNS |> List.map (fun (_, k) -> if k = "lead_id" then asNumberIfInt (get r k) else orEmpty (get r k)))))
    book (sprintf "TransferCheck_%s_%s.xlsx" (rawText (get range "start")) (rawText (get range "end"))) [ summary; detail ]
