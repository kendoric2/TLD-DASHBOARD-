module Tld.Dates

// The date ranges TLD reports run over: the presets (Today, This Week, This
// Month, Last Month, This Quarter) and a custom From/To, plus the label a page
// shows for each. Shared, so every report reads "This Week" the same way.
//
// Ported from the dashboard's date_range_for and _resolve_range. Today is an
// argument, never read here. The shell passes today in Eastern time, which is
// where the agents are; the Python read the server's clock, and on Vercel that
// is UTC, so after 8 PM Eastern its "today" was already tomorrow.

open System

let private MAX_RANGE_DAYS = 366 // a custom range is capped at about 12 months

let private MONTHS =
    [| "Jan"; "Feb"; "Mar"; "Apr"; "May"; "Jun"; "Jul"; "Aug"; "Sep"; "Oct"; "Nov"; "Dec" |]

let private LABELS =
    [ "today", "Today"
      "this_week", "This Week"
      "this_month", "This Month"
      "last_month", "Last Month"
      "this_quarter", "This Quarter" ]
    |> Map.ofList

let private pad2 (n: int) = if n < 10 then "0" + string n else string n

let iso (d: DateTime) = sprintf "%d-%s-%s" d.Year (pad2 d.Month) (pad2 d.Day)

// Strictly YYYY-MM-DD and a real calendar day, else None
let parseIso (value: string) : DateTime option =
    if isNull value then None
    else
        let s = value.Trim()
        let digits (a: int) (b: int) = s.Substring(a, b) |> Seq.forall Char.IsDigit

        if s.Length = 10 && s.[4] = '-' && s.[7] = '-' && digits 0 4 && digits 5 2 && digits 8 2 then
            let y, m, d = int (s.Substring(0, 4)), int (s.Substring(5, 2)), int (s.Substring(8, 2))
            if m >= 1 && m <= 12 && d >= 1 && d <= DateTime.DaysInMonth(y, m) then Some(DateTime(y, m, d))
            else None
        else
            None

// Monday of this week through today, matching Python's weekday() where Monday is 0
let private mondayOf (d: DateTime) = d.AddDays(-(float ((int d.DayOfWeek + 6) % 7)))

(*-------- This is critical --------*)
(*
 Unknown keys fall to This Month, exactly as the Python did. The page only ever
 sends the five keys below, so the fallback exists for a hand typed url and
 should never decide a real number.
*)
let rangeFor (key: string) (today: DateTime) : DateTime * DateTime =
    match key with
    | "today" -> today, today
    | "this_week" -> mondayOf today, today
    | "last_month" ->
        let lastDay = DateTime(today.Year, today.Month, 1).AddDays(-1.0)
        DateTime(lastDay.Year, lastDay.Month, 1), lastDay
    | "this_quarter" -> DateTime(today.Year, 3 * ((today.Month - 1) / 3) + 1, 1), today
    | _ -> DateTime(today.Year, today.Month, 1), today

let private day (d: DateTime) = sprintf "%s %d" MONTHS.[d.Month - 1] d.Day

// "Jun 1 – Jun 15, 2026", and friendly names for a single recent day
let customLabel (a: DateTime) (b: DateTime) (today: DateTime) =
    if a = b then
        if a = today then "Today"
        elif a = today.AddDays(-1.0) then "Yesterday"
        else sprintf "%s, %d" (day a) a.Year
    elif a.Year = b.Year then
        sprintf "%s – %s, %d" (day a) (day b) b.Year
    else
        sprintf "%s, %d – %s, %d" (day a) a.Year (day b) b.Year

(*=======================================================
        THE ONE CALL THE SHELL MAKES
========================================================*)

type RangeInput =
    abstract range: string
    abstract start: string
    abstract ``end``: string
    abstract today: string

(*
 What a request's range resolves to. error is null when the range is good, and
 the message the page shows when it is not. A plain object, so a route can
 hand error straight back as the JSON the page already expects.
*)
let resolveRange (input: RangeInput) =
    let fail (message: string) = {| start = null; ``end`` = null; label = null; error = message |}
    let ok (a: DateTime) (b: DateTime) (label: string) = {| start = iso a; ``end`` = iso b; label = label; error = null |}

    match parseIso input.today with
    | None -> fail "The server did not supply today's date."
    | Some today ->
        let key = if String.IsNullOrEmpty input.range then "today" else input.range

        if key = "custom" then
            match parseIso input.start, parseIso input.``end`` with
            | Some a, Some b when b < a -> fail "End date can't be before the start date."
            | Some a, Some b when (b - a).TotalDays > float MAX_RANGE_DAYS -> fail "Custom range can't exceed 12 months."
            | Some a, Some b -> ok a b (customLabel a b today)
            | _ -> fail "Custom range needs a valid start and end date (YYYY-MM-DD)."
        else
            let a, b = rangeFor key today
            ok a b (LABELS |> Map.tryFind key |> Option.defaultValue "Today")
