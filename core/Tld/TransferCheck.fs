module Tld.TransferCheck

// The Transfer Check: match the fronters' transfers from DialedIN against TLD
// to see which ones sold and who gets paid.
//
// The fronters transfer calls from DialedIN into TLD, but TLD attaches each
// transfer to whatever lead already owns that phone (most of these people were
// bought last AEP under another vendor), so transfers never show under the
// MAPD / Manhattan Life vendors. This works backwards from DialedIN's own list:
//
//   1. LEADS     every TLD lead on each phone, plus linked leads both ways
//   2. CALLS     the inbound call that was the transfer
//   3. POLICIES  every policy on those leads
//
// A transfer is PAID when one of the phone's leads has a new policy created
// after the transfer (to the minute) and on the same day, verified by a manager
// (TLD's `verified` flag). Callbacks and a different enrolling agent are fine;
// enrollments are meant to finish on an inbound call. A sale on a later day is
// LATER DAY, NOT PAID. Not verified yet is AWAITING VERIFICATION; "Sale Made"
// on the call with no policy yet is PENDING.
//
// Ported from the TLD dashboard's transfer_check.py. The shell runs the steps
// in order and fetches what each asks for; nothing here touches the network.
// PRIVACY: the files carry MBI, DOB and Medicaid numbers. Only phone, rep,
// campaign, time and TLD lead id are read, and results show a phone's last 4.

open System
open System.Collections.Generic
open System.Text.RegularExpressions
open Fable.Core
open Fable.Core.JsInterop
open Tld.Rows

let PAY_ONCE_PER_TRANSFER = true // once per transfer however many policies it produced; payroll's call
let private MATCH_WINDOW = 3.0 * 3600.0 // a call within this of the file's time can be the transfer
let private CALL_SLACK = 60.0 // TLD's call can start a few seconds after the file's time
let RESULT_LATER_DAY = "Later day – not paid"
let private UNPAID_STATUSES = set [ "trash"; "quoted"; "unsold"; "cancelled"; "canceled"; "declined" ]
let private VERIFIED = set [ "1"; "1.0"; "True"; "true" ]
let BATCH = 100 // phones or leads per request
let POLICY_BATCH = 50 // leads per policies request
let LIST_REP = "(fronter list)"

(*
 Product line, for reporting only; it never decides who is paid. A sale is
 labelled by its carrier, because the campaign the fronter dialed and what
 sold disagree (4 of the first 36 sales were Manhattan Life off MAPD).
 Manhattan Life and GTL go together; everything else is MAPD, so a new MAPD
 carrier needs no change here.
*)
let LINE_MANHATTAN = "Manhattan Life"
let LINE_MAPD = "MAPD"
let private MANHATTAN_CARRIERS = set [ "MANHATTAN"; "MANHATTAN LIFE"; "MANHATTANLIFE"; "GTL" ]

let carrierLine (name: obj) =
    let key = Regex.Replace((rawText name).ToUpperInvariant(), "[^A-Z ]", "").Trim()
    if key = "" then "" elif MANHATTAN_CARRIERS.Contains key then LINE_MANHATTAN else LINE_MAPD

let campaignLine (name: string) =
    let key = (if isNull name then "" else name).ToUpperInvariant()
    if key.Contains "MANHATTAN" then LINE_MANHATTAN elif key.Contains "MAPD" then LINE_MAPD else ""

(*=======================================================
        TIME WITHOUT A TIMEZONE
========================================================*)

(*-------- This is critical --------*)
(*
 DialedIN's and TLD's times are wall clock with no zone, and the Python
 compared them that way. A JavaScript Date would put them in the server's zone
 and lose or gain an hour across a daylight saving change, moving a sale to
 the wrong side of its transfer. So a time here is plain seconds counted from
 a fixed day, and a date is its YYYY-MM-DD.
*)
let private daysFromCivil (y: int) (m: int) (d: int) =
    let y = if m <= 2 then y - 1 else y
    let era = (if y >= 0 then y else y - 399) / 400
    let yoe = y - era * 400
    let doy = (153 * ((m + 9) % 12) + 2) / 5 + d - 1
    era * 146097 + (yoe * 365 + yoe / 4 - yoe / 100 + doy) - 719468

let private civilFromDays (days: int) =
    let z = days + 719468
    let era = (if z >= 0 then z else z - 146096) / 146097
    let doe = z - era * 146097
    let yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100)
    let mp = (5 * doy + 2) / 153
    let d = doy - (153 * mp + 2) / 5 + 1
    let m = if mp < 10 then mp + 3 else mp - 9
    (if m <= 2 then yoe + era * 400 + 1 else yoe + era * 400), m, d

let private pad2 (n: int) = if n < 10 then "0" + string n else string n

let dayOf (seconds: float) =
    let y, m, d = civilFromDays (int (floor (seconds / 86400.0)))
    sprintf "%d-%s-%s" y (pad2 m) (pad2 d)

let formatTime (seconds: float) =
    let s = int (seconds - floor (seconds / 86400.0) * 86400.0)
    sprintf "%s %s:%s:%s" (dayOf seconds) (pad2 (s / 3600)) (pad2 (s % 3600 / 60)) (pad2 (s % 60))

let private stamp y mo d h mi s =
    if mo < 1 || mo > 12 || d < 1 || d > DateTime.DaysInMonth(y, mo) || h > 23 || mi > 59 || s > 59 then None
    else Some(float (daysFromCivil y mo d) * 86400.0 + float (h * 3600 + mi * 60 + s))

// The formats DialedIN and TLD have used, tried in the Python's order
let private FORMATS =
    [ @"^(\d{1,2})/(\d{1,2})/(\d{4})\s+(\d{1,2}):(\d{1,2}):(\d{1,2})\s+([AaPp][Mm])$", "mdY IMS p"
      @"^(\d{1,2})/(\d{1,2})/(\d{4})\s+(\d{1,2}):(\d{1,2})\s+([AaPp][Mm])$", "mdY IM p"
      @"^(\d{1,2})/(\d{1,2})/(\d{4})\s+(\d{1,2}):(\d{1,2}):(\d{1,2})$", "mdY HMS"
      @"^(\d{1,2})/(\d{1,2})/(\d{4})\s+(\d{1,2}):(\d{1,2})$", "mdY HM"
      @"^(\d{4})-(\d{1,2})-(\d{1,2})\s+(\d{1,2}):(\d{1,2}):(\d{1,2})$", "Ymd HMS"
      @"^(\d{1,2})/(\d{1,2})/(\d{4})$", "mdY"
      @"^(\d{4})-(\d{1,2})-(\d{1,2})$", "Ymd" ]
    |> List.map (fun (pattern, kind) -> Regex(pattern), kind)

[<Emit("($0 instanceof Date)")>]
let private isDate (value: obj) : bool = jsNative

[<Emit("[$0.getUTCFullYear(), $0.getUTCMonth() + 1, $0.getUTCDate(), $0.getUTCHours(), $0.getUTCMinutes(), $0.getUTCSeconds()]")>]
let private dateParts (value: obj) : int array = jsNative

(*
 Python's _parse_dt. A Date (an Excel cell, read by the shell as the wall time
 it shows, in UTC fields) is taken as is; text is tried against each format.
*)
let parseTime (value: obj) : float option =
    if isDate value then
        let p = dateParts value
        stamp p.[0] p.[1] p.[2] p.[3] p.[4] p.[5]
    else
        let s = (rawText value).Trim()
        FORMATS
        |> List.tryPick (fun (re, kind) ->
            let m = re.Match s
            if not m.Success then None
            else
                let g (i: int) = int m.Groups.[i].Value
                let hour12 (h: int) (ampm: string) =
                    if h < 1 || h > 12 then 99
                    elif ampm.ToUpperInvariant() = "AM" then (if h = 12 then 0 else h)
                    else (if h = 12 then 12 else h + 12)
                match kind with
                | "mdY IMS p" -> stamp (g 3) (g 1) (g 2) (hour12 (g 4) m.Groups.[7].Value) (g 5) (g 6)
                | "mdY IM p" -> stamp (g 3) (g 1) (g 2) (hour12 (g 4) m.Groups.[6].Value) (g 5) 0
                | "mdY HMS" -> stamp (g 3) (g 1) (g 2) (g 4) (g 5) (g 6)
                | "mdY HM" -> stamp (g 3) (g 1) (g 2) (g 4) (g 5) 0
                | "Ymd HMS" -> stamp (g 1) (g 2) (g 3) (g 4) (g 5) (g 6)
                | "mdY" -> stamp (g 3) (g 1) (g 2) 0 0 0
                | _ -> stamp (g 1) (g 2) (g 3) 0 0 0)

(*=======================================================
        READING THE FILE
========================================================*)

// The last 10 digits, or "" if there are fewer
let phone10 (value: obj) =
    let digits = Regex.Replace(rawText value, @"\D", "")
    if digits.Length >= 10 then digits.Substring(digits.Length - 10) else ""

let private PHONE = [ "PrimaryPhone"; "Phone"; "Phone Number" ]
let private REP = [ "Rep"; "Agent"; "Fronter" ]
let private CAMPAIGN = [ "Campaign" ]
let private WHEN = [ "CallDate"; "LastUpdated"; "Date" ]
// Never plain "Lead ID": in CallDetails that is DialedIN's own id, the same 9
// digits as a TLD lead id but a different number (0 of 40 matched on 10/5-10/9)
let private TLD_ID = [ "TLD Lead ID"; "TLD Lead Id" ]

(*
 CallDetails logs every transfer twice: the fronter's leg ("Transferred Call",
 Rep = the fronter) and the line's leg ("Blind Transfer", Rep = the transfer
 line's number). Only the fronter's leg is a transfer.
*)
let private DETAILS = "Details"
let private FRONTER_DETAILS = "transferred call"

(*
 BlindTransfer puts the transfer LINE in Phone (3 numbers across 1,566 rows on
 10/15-10/18) and the customer in Caller ID. When Phone holds only a handful of
 numbers, they are the lines.
*)
let private CALLER_ID = "Caller ID"
let private LINE_PHONES_MAX = 5

type Transfer =
    { phone: string
      rep: string
      campaign: string
      time: float option
      tldId: string
      listed: bool }

// A header by any of its names, case and spacing aside; a header named twice is the later one
let private pick (header: string array) (names: string list) =
    let low = Dictionary<string, string>()
    for h in header do
        low.[h.Trim().ToLowerInvariant()] <- h
    names |> List.tryPick (fun n -> match low.TryGetValue(n.ToLowerInvariant()) with | true, h -> Some h | _ -> None)

let private field (r: Row) (col: string option) = match col with Some c -> text r c | None -> ""

(*
 A DialedIN export (CallDetails, BlindTransfer, or an older lead export), or
 with phoneList the fronters' own list: phone numbers only, deduplicated (164
 of 1,344 were listed twice on 10/15-10/17), timed later from TLD. error is
 null when the file reads; the message the page shows when it does not.
*)
let readFile (header: string array) (records: Row array) (phoneList: bool) =
    let fail (message: string) = {| transfers = [||]; error = message |}
    let header = if isNull header then [||] else header
    let records = if isNull records then [||] else records |> Array.filter isObject
    let phoneCol, repCol, campaignCol = pick header PHONE, pick header REP, pick header CAMPAIGN
    let whenCol, tldCol = pick header WHEN, pick header TLD_ID

    if phoneList then
        match phoneCol with
        | None -> fail "This list needs a phone column (Phone or Phone Number)."
        | Some col ->
            let seen = HashSet<string>()
            let out =
                records
                |> Array.choose (fun r ->
                    let phone = phone10 (get r col)
                    if phone = "" || not (seen.Add phone) then None
                    else
                        Some
                            { phone = phone
                              rep = (match field r repCol with "" -> LIST_REP | rep -> rep)
                              campaign = field r campaignCol
                              time = None
                              tldId = ""
                              listed = true })
            if Array.isEmpty out then fail "No rows with a phone number were found in that file."
            else {| transfers = out; error = null |}
    else
        match phoneCol, whenCol with
        | Some phoneCol, Some whenCol ->
            let records =
                match pick header [ DETAILS ] with
                | Some d when records |> Array.exists (fun r -> (text r d).ToLowerInvariant() = FRONTER_DETAILS) ->
                    records |> Array.filter (fun r -> (text r d).ToLowerInvariant() = FRONTER_DETAILS)
                | _ -> records
            let phoneCol =
                match pick header [ CALLER_ID ] with
                | Some callerId when records.Length > 20 ->
                    let phones = records |> Array.map (fun r -> phone10 (get r phoneCol)) |> Array.filter ((<>) "") |> Array.distinct
                    if phones.Length <= LINE_PHONES_MAX then callerId else phoneCol
                | _ -> phoneCol
            let out =
                records
                |> Array.choose (fun r ->
                    let phone = phone10 (get r phoneCol)
                    if phone = "" then None
                    else
                        Some
                            { phone = phone
                              rep = field r repCol
                              campaign = field r campaignCol
                              time = parseTime (get r whenCol)
                              tldId = (match tldCol with Some c -> Regex.Replace(rawText (get r c), @"\D", "") | None -> "")
                              listed = false })
            if Array.isEmpty out then fail "No rows with a phone number were found in that file."
            else {| transfers = out; error = null |}
        | _ ->
            fail
                "This doesn't look like a DialedIN export — it needs a phone column (PrimaryPhone or Phone) and a date column (CallDate or Date). For the fronters' own list, use \"Check fronter list\" instead."

// A pay week date from the form: "" is none, anything else must be YYYY-MM-DD
let readDate (name: string) (value: string) =
    let v = if isNull value then "" else value.Trim()
    if v = "" then {| value = ""; error = null |}
    else
        match Dates.parseIso v with
        | Some d -> {| value = Dates.iso d; error = null |}
        | None -> {| value = ""; error = sprintf "Could not read the %s date '%s'. Use YYYY-MM-DD." name v |}

(*=======================================================
        THE FRONTERS' OWN LIST
========================================================*)

let listRange (start: string) (finish: string) =
    if String.IsNullOrEmpty start || String.IsNullOrEmpty finish then
        "The fronter list has no dates of its own — pick the From and To dates first."
    elif start > finish then "The start date is after the end date."
    else null

(*
 One entry per number per day it called in to TLD in the range, timed at that
 day's first inbound call. A number that never called in stays as one undated
 entry and ends up Not found.
*)
let timeList (listed: Transfer array) (callRows: Row array) =
    let calls = Dictionary<string, ResizeArray<float>>()
    for r in callRows |> Array.filter isObject do
        match phone10 (get r "phone_number"), parseTime (get r "call_date") with
        | "", _ | _, None -> ()
        | p, Some t ->
            if not (calls.ContainsKey p) then calls.[p] <- ResizeArray()
            calls.[p].Add t
    listed
    |> Array.collect (fun t ->
        match calls.TryGetValue t.phone with
        | true, times when times.Count > 0 ->
            times
            |> Seq.groupBy dayOf
            |> Seq.map (fun (day, ts) -> day, Seq.min ts)
            |> Seq.sortBy fst
            |> Seq.map (fun (_, first) -> { t with time = Some first })
            |> Array.ofSeq
        | _ -> [| t |])

(*=======================================================
        THE RANGE
========================================================*)

type Prepared =
    { transfers: Transfer array
      dropped: int
      droppedRows: Transfer array
      d0: string
      d1: string
      fileD0: string
      fileD1: string }

(*-------- This is critical --------*)
(*
 The pay week wins over the file. DialedIN filters its export on the lead's
 date but stamps CallDate with the last call attempt, so a 9/28-10/4 file
 carried 267 transfers from 10/6-10/7. Rows outside the week are dropped and
 counted, and dropped rows that already sold are reported (droppedSales), so
 paid work never falls out of a week silently. With no week chosen, the file's
 own first and last day are the range.
*)
let prepare (transfers: Transfer array) (start: string) (finish: string) =
    let fail (message: string) = {| prepared = (null: obj); error = message |}
    let ok (p: Prepared) = {| prepared = box p; error = null |}
    if transfers |> Array.exists (fun t -> t.listed) then
        ok { transfers = transfers; dropped = 0; droppedRows = [||]; d0 = start; d1 = finish; fileD0 = start; fileD1 = finish }
    else
        let times = transfers |> Array.choose (fun t -> t.time)
        if Array.isEmpty times then fail "None of the CallDate values could be read as a date."
        else
            let fileD0, fileD1 = dayOf (Array.min times), dayOf (Array.max times)
            if String.IsNullOrEmpty start && String.IsNullOrEmpty finish then
                ok { transfers = transfers; dropped = 0; droppedRows = [||]; d0 = fileD0; d1 = fileD1; fileD0 = fileD0; fileD1 = fileD1 }
            else
                let d0 = if String.IsNullOrEmpty start then fileD0 else start
                let d1 = if String.IsNullOrEmpty finish then fileD1 else finish
                if d0 > d1 then fail "The start date is after the end date."
                else
                    let inside t = match t.time with Some s -> d0 <= dayOf s && dayOf s <= d1 | None -> false
                    let kept = transfers |> Array.filter inside
                    let droppedRows = transfers |> Array.filter (fun t -> t.time.IsSome && not (inside t))
                    if Array.isEmpty kept then
                        fail (sprintf "No transfers fall in %s to %s. This file covers %s to %s (%d rows)." d0 d1 fileD0 fileD1 transfers.Length)
                    else
                        ok { transfers = kept; dropped = transfers.Length - kept.Length; droppedRows = droppedRows
                             d0 = d0; d1 = d1; fileD0 = fileD0; fileD1 = fileD1 }

// Every phone once, sorted, which is the order the lookups go in
let phonesOf (transfers: Transfer array) = transfers |> Array.map (fun t -> t.phone) |> Array.distinct |> Array.sort

let batches (size: int) (items: string array) = items |> Array.chunkBySize size

// A day of slack each side for the call lookup
let callWindow (d0: string) (d1: string) =
    let shift (iso: string) (days: float) = Dates.parseIso iso |> Option.map (fun d -> Dates.iso (d.AddDays days)) |> Option.defaultValue iso
    [| shift d0 -1.0; shift d1 1.0 |]

(*=======================================================
        THE LOOKUPS, TURNED INTO MAPS
========================================================*)

let private hasId (value: obj) = match textOf value with "" | "0" | "None" -> false | _ -> true

(*
 phone -> every lead on it, and any lead those are linked to. A linked lead
 can carry a different phone, so the phone lookup alone would miss a sale
 written on it.
*)
let leadsMap (rows: Row array) =
    let map = Dictionary<string, ResizeArray<string>>()
    for r in rows |> Array.filter isObject do
        let p = phone10 (get r "phone")
        if p <> "" && textOf (get r "lead_id") <> "" then
            if not (map.ContainsKey p) then map.[p] <- ResizeArray()
            let ids = map.[p]
            let add id = if not (ids.Contains id) then ids.Add id
            add (textOf (get r "lead_id"))
            if hasId (get r "linked_lead_id") then add (textOf (get r "linked_lead_id"))
    map

// The other direction: a policy in the range on a lead linked TO one of these phones' leads
let addLinkedBack (map: Dictionary<string, ResizeArray<string>>) (rows: Row array) =
    let phoneOf = Dictionary<string, string>()
    for KeyValue(p, ids) in map do
        for id in ids do
            phoneOf.[id] <- p
    for r in rows |> Array.filter isObject do
        let lid = textOf (get r "lead_id")
        match phoneOf.TryGetValue(textOf (get r "lead_linked_lead_id")) with
        | true, p when lid <> "" && not (map.[p].Contains lid) -> map.[p].Add lid
        | _ -> ()
    map

let callsMap (rows: Row array) =
    let map = Dictionary<string, ResizeArray<Row>>()
    for r in rows |> Array.filter isObject do
        let p = phone10 (get r "phone_number")
        if p <> "" then
            if not (map.ContainsKey p) then map.[p] <- ResizeArray()
            map.[p].Add r
    map

// Every lead id to fetch policies for, sorted, which decides the batches
let leadIdsOf (map: Dictionary<string, ResizeArray<string>>) (transfers: Transfer array) =
    Seq.append (map.Values |> Seq.collect id) (transfers |> Seq.map (fun t -> t.tldId))
    |> Seq.filter ((<>) "")
    |> Seq.distinct
    |> Seq.sort
    |> Array.ofSeq

// lead -> its policies, one batch at a time; a policy id seen twice in a batch counts once
let policiesMap (batchResults: Row array array) =
    let map = Dictionary<string, ResizeArray<Row>>()
    for rows in batchResults do
        let seen = HashSet<string>()
        for r in (if isNull rows then [||] else rows) |> Array.filter isObject do
            let pid = rawText (get r "policy_id")
            if not (pid <> "" && seen.Contains pid) then
                seen.Add pid |> ignore
                let lead = textOf (get r "lead_id")
                if not (map.ContainsKey lead) then map.[lead] <- ResizeArray()
                map.[lead].Add r
    map

(*=======================================================
        SCORING
========================================================*)

let private isLive (p: Row) = not (UNPAID_STATUSES.Contains((text p "status_name").ToLowerInvariant()))
let private isVerified (p: Row) = VERIFIED.Contains(text p "verified")

(*
 The inbound call that IS the transfer: within MATCH_WINDOW of the file's time,
 the latest one starting no more than CALL_SLACK after it (an export can stamp
 a transfer late, never early), else the nearest after. BlindTransfer stamps up
 to an hour late; CallDetails is within seconds.
*)
let private matchCall (t: Transfer) (calls: ResizeArray<Row>) =
    match t.time with
    | None -> None
    | Some at ->
        let timed =
            calls
            |> Seq.choose (fun c -> parseTime (get c "call_date") |> Option.map (fun cd -> cd, c))
            |> Seq.filter (fun (cd, _) -> abs (cd - at) <= MATCH_WINDOW)
            |> List.ofSeq
        match timed |> List.filter (fun (cd, _) -> cd <= at + CALL_SLACK) with
        | [] -> timed |> List.fold (fun best x -> match best with Some (b, _) when fst x >= b -> best | _ -> Some x) None |> Option.map snd
        | before -> before |> List.fold (fun best x -> match best with Some (b, _) when fst x <= b -> best | _ -> Some x) None |> Option.map snd

let private joinSorted (values: string seq) = values |> Seq.filter ((<>) "") |> Seq.distinct |> Seq.sort |> String.concat ", "

(*-------- This is critical --------*)
(*
 Who gets the sale. Every new policy on a phone's leads goes to the LATEST
 transfer of that phone made before the policy was created, to the minute, so
 two fronters are never paid for one sale, and an 11 AM sale is never paid to
 a 3 PM transfer. A policy created after the range's last day belongs to a
 later run: the lookup has no date filter, and without this cap any future
 policy on the phone's leads would be credited back.
*)
let score
    (prepared: Prepared)
    (leads: Dictionary<string, ResizeArray<string>>)
    (calls: Dictionary<string, ResizeArray<Row>>)
    (policies: Dictionary<string, ResizeArray<Row>>)
    (droppedSales: obj)
    =
    let ts = prepared.transfers
    let callOf =
        ts |> Array.map (fun t -> match calls.TryGetValue t.phone with | true, cs -> matchCall t cs | _ -> None)
    let at =
        ts |> Array.mapi (fun i t ->
            match callOf.[i] |> Option.bind (fun c -> parseTime (get c "call_date")) with
            | Some s -> Some s
            | None -> t.time)

    let credited = Dictionary<int, ResizeArray<Row>>()
    let byPhone = Dictionary<string, ResizeArray<int>>()
    let phoneOrder = ResizeArray<string>()
    ts |> Array.iteri (fun i t ->
        if not (byPhone.ContainsKey t.phone) then
            phoneOrder.Add t.phone
            byPhone.[t.phone] <- ResizeArray()
        byPhone.[t.phone].Add i)
    for phone in phoneOrder do
        let idxs = byPhone.[phone]
        let ids =
            Seq.append (match leads.TryGetValue phone with | true, l -> l :> seq<string> | _ -> Seq.empty) (idxs |> Seq.map (fun i -> ts.[i].tldId))
            |> Seq.filter ((<>) "")
            |> Seq.distinct
        for lid in ids do
            match policies.TryGetValue lid with
            | true, ps ->
                for p in ps do
                    match parseTime (get p "date_created") with
                    | Some created when dayOf created <= prepared.d1 ->
                        let owner =
                            idxs
                            |> Seq.filter (fun i -> match at.[i] with Some a -> a <= created | None -> false)
                            |> Seq.fold (fun best i -> match best with Some b when at.[i].Value <= at.[b].Value -> best | _ -> Some i) None
                        match owner with
                        | Some o ->
                            if not (credited.ContainsKey o) then credited.[o] <- ResizeArray()
                            credited.[o].Add p
                        | None -> ()
                    | _ -> ()
            | _ -> ()

    let rows =
        ts |> Array.mapi (fun i t ->
            let call = callOf.[i]
            let callText key = match call with Some c -> text c key | None -> ""
            let fresh =
                (match credited.TryGetValue i with | true, ps -> List.ofSeq ps | _ -> [])
                |> List.sortBy (fun p -> rawText (get p "date_created"))
            let live = fresh |> List.filter isLive
            let disposition = callText "status_name"
            let leadId =
                match callText "lead_vendor_lead_code", t.tldId with
                | "", "" -> (match leads.TryGetValue t.phone with | true, l when l.Count > 0 -> l.[l.Count - 1] | _ -> "")
                | "", tld -> tld
                | code, _ -> code
            // same day rule: the first new policy has to be written the day of the transfer
            let laterDay =
                not live.IsEmpty
                && dayOf (live |> List.map (fun p -> (parseTime (get p "date_created")).Value) |> List.min) <> dayOf at.[i].Value
            let paid = if laterDay then [] else live |> List.filter isVerified
            let result =
                if laterDay then RESULT_LATER_DAY
                elif not paid.IsEmpty then "Paid"
                elif not live.IsEmpty then "Awaiting verification"
                elif disposition.ToLowerInvariant() = "sale made" then "Pending"
                elif call.IsNone then "Not found"
                else "No sale"
            let shown = if not paid.IsEmpty then paid elif not live.IsEmpty then live else fresh
            let saleLines = shown |> List.map (fun p -> carrierLine (get p "carrier_name")) |> joinSorted
            let soldOn =
                shown
                |> List.map (fun p -> rawText (get p "date_sold"))
                |> List.filter (fun s -> let head = (if s.Length > 4 then s.Substring(0, 4) else s) in head <> "" && head <> "None" && head <> "0000")
                |> List.map (fun s -> if s.Length > 10 then s.Substring(0, 10) else s)
            {| rep = (if t.rep = "" then "(no rep)" else t.rep)
               campaign = t.campaign
               product_line = (if saleLines = "" then campaignLine t.campaign else saleLines)
               sale_lines = saleLines
               pol_manhattan = paid |> List.filter (fun p -> carrierLine (get p "carrier_name") = LINE_MANHATTAN) |> List.length
               pol_mapd = paid |> List.filter (fun p -> carrierLine (get p "carrier_name") = LINE_MAPD) |> List.length
               phone_last4 = t.phone.Substring(t.phone.Length - 4)
               transfer_time = (match t.time with Some s -> formatTime s | None -> "")
               lead_id = leadId
               call_time = (match call with Some c -> rawText (get c "call_date") | None -> "")
               agent = callText "agent_name"
               disposition = disposition
               landed_vendor = callText "vendor_description"
               line = callText "did_description"
               result = result
               policies = paid.Length
               carrier = shown |> List.map (fun p -> text p "carrier_name") |> joinSorted
               verified_by = paid |> List.map (fun p -> text p "verifier_name") |> List.filter ((<>) "None") |> joinSorted
               policy_status = shown |> List.map (fun p -> text p "status_name") |> joinSorted
               date_sold = (if soldOn.IsEmpty then "" else List.min soldOn) |})

    let countIf (pred: 'a -> bool) (rs: 'a array) = rs |> Array.filter pred |> Array.length

    let repOrder = rows |> Array.map (fun r -> r.rep) |> Array.distinct
    let byRep =
        repOrder
        |> Array.map (fun rep ->
            let mine = rows |> Array.filter (fun r -> r.rep = rep)
            let paid = mine |> countIf (fun r -> r.result = "Paid")
            let policyCount = mine |> Array.sumBy (fun r -> r.policies)
            {| rep = rep
               transfers = mine.Length
               found = mine |> countIf (fun r -> r.result <> "Not found")
               paid = paid
               policies = policyCount
               awaiting = mine |> countIf (fun r -> r.result = "Awaiting verification")
               pending = mine |> countIf (fun r -> r.result = "Pending")
               later_day = mine |> countIf (fun r -> r.result = RESULT_LATER_DAY)
               not_found = mine |> countIf (fun r -> r.result = "Not found")
               pol_manhattan = mine |> Array.sumBy (fun r -> r.pol_manhattan)
               pol_mapd = mine |> Array.sumBy (fun r -> r.pol_mapd)
               payable = (if PAY_ONCE_PER_TRANSFER then paid else policyCount) |})
        |> List.ofArray
        |> List.sortWith (fun a b ->
            match compare b.payable a.payable with
            | 0 ->
                match compare b.transfers a.transfers with
                | 0 -> compare (a.rep.ToLowerInvariant()) (b.rep.ToLowerInvariant())
                | c -> c
            | c -> c)
        |> Array.ofList

    let sum (f: _ -> int) = byRep |> Array.sumBy f
    let totals =
        {| transfers = sum (fun f -> f.transfers); found = sum (fun f -> f.found); paid = sum (fun f -> f.paid)
           policies = sum (fun f -> f.policies); awaiting = sum (fun f -> f.awaiting); pending = sum (fun f -> f.pending)
           later_day = sum (fun f -> f.later_day); not_found = sum (fun f -> f.not_found); payable = sum (fun f -> f.payable)
           pol_manhattan = sum (fun f -> f.pol_manhattan); pol_mapd = sum (fun f -> f.pol_mapd) |}

    // Per product line, grouped on the sale's carrier or, with no sale, the campaign's line
    let lineOf (r: {| product_line: string |}) = if r.product_line = "" then "(unknown)" else r.product_line
    let byLine =
        rows
        |> Array.map (fun r -> lineOf {| product_line = r.product_line |})
        |> Array.distinct
        |> Array.map (fun line ->
            let mine = rows |> Array.filter (fun r -> lineOf {| product_line = r.product_line |} = line)
            {| line = line
               transfers = mine.Length
               paid = mine |> countIf (fun r -> r.result = "Paid")
               policies = mine |> Array.sumBy (fun r -> r.policies)
               awaiting = mine |> countIf (fun r -> r.result = "Awaiting verification")
               pending = mine |> countIf (fun r -> r.result = "Pending")
               later_day = mine |> countIf (fun r -> r.result = RESULT_LATER_DAY)
               not_found = mine |> countIf (fun r -> r.result = "Not found") |})
        |> List.ofArray
        |> List.sortWith (fun a b ->
            match compare b.policies a.policies with
            | 0 ->
                match compare b.transfers a.transfers with
                | 0 -> compare a.line b.line
                | c -> c
            | c -> c)
        |> Array.ofList

    {| range ={| start = prepared.d0; ``end`` = prepared.d1 |}
       file_range = {| start = prepared.fileD0; ``end`` = prepared.fileD1 |}
       dropped = prepared.dropped
       dropped_sales = droppedSales
       pay_once = PAY_ONCE_PER_TRANSFER
       totals = totals
       by_rep = byRep
       by_line = byLine
       rows = rows |> List.ofArray |> List.sortWith (fun a b -> compare b.transfer_time a.transfer_time) |> Array.ofList |}

(*
 The guard for the pay week: do any transfers the range threw away already
 have a sale? Same test as a sale (a live new policy created on or after the
 transfer day) with no upper cap, since these belong to another week's run.
 Before the week should have been in the last run; after belongs to the next.
*)
let droppedSales
    (dropped: Transfer array)
    (leads: Dictionary<string, ResizeArray<string>>)
    (policies: Dictionary<string, ResizeArray<Row>>)
    (d0: string)
    : obj =
    if Array.isEmpty dropped then null
    else
        let hits =
            dropped
            |> Array.choose (fun t ->
                let day = dayOf t.time.Value
                let lids =
                    Seq.append (match leads.TryGetValue t.phone with | true, l -> l :> seq<string> | _ -> Seq.empty) [ t.tldId ]
                    |> Seq.filter ((<>) "")
                    |> Seq.distinct
                let sold =
                    lids
                    |> Seq.collect (fun lid -> match policies.TryGetValue lid with | true, ps -> ps :> seq<Row> | _ -> Seq.empty)
                    |> Seq.filter (fun p ->
                        isLive p && (match parseTime (get p "date_created") with Some c -> dayOf c >= day | None -> false))
                    |> List.ofSeq
                if sold.IsEmpty then None
                else Some((if day < d0 then "before" else "after"), day, sold |> List.exists isVerified))
        let side (name: string) =
            let mine = hits |> Array.filter (fun (s, _, _) -> s = name)
            if Array.isEmpty mine then []
            else
                let days = mine |> Array.map (fun (_, d, _) -> d) |> Array.sort
                [ name,
                  box
                      {| transfers = mine.Length
                         verified = mine |> Array.filter (fun (_, _, v) -> v) |> Array.length
                         first = days.[0]
                         last = days.[days.Length - 1] |} ]
        let parts = side "before" @ side "after"
        createObj (("transfers", box hits.Length) :: parts)
