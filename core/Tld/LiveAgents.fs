module Tld.LiveAgents

// The live board: who is logged in to the dialer right now and what they are
// doing, with each person's role from the CRM and, mid call, the lead they are
// on. Not a roster; anyone logged out does not appear.
//
// Ported from the TLD dashboard's live_agents. The requests are
// Tld.Queries.liveAgents, crmUsers and leadsByPhone.

open System.Collections.Generic
open Fable.Core.JsInterop
open Tld.Rows

let private LABELS =
    dict [ "READY", "Ready"; "INCALL", "On a call"; "PAUSED", "Paused"; "DISPO", "Wrapping up"; "DEAD", "Disconnected" ]

// Calls in progress and wrap up first, what a supervisor scans for, then ready, paused, dropped lines last
let private ORDER = dict [ "INCALL", 0; "DISPO", 1; "READY", 2; "PAUSED", 3; "DEAD", 4 ]

let private LEADS_PER_PHONE = 20 // a phone can match several leads over time

// "1:02:03" to seconds; anything that is not exactly 3 whole numbers is 0, as int() decided it
let private durationSeconds (value: obj) =
    let s = (orElse (box "0:0:0") value) |> rawText
    let parts = s.Split(':')
    let whole (p: string) =
        let t = p.Trim()
        let digits = if t.StartsWith "+" || t.StartsWith "-" then t.Substring 1 else t
        if digits <> "" && digits |> Seq.forall System.Char.IsDigit then Some(int t) else None
    match parts |> Array.map whole with
    | [| Some h; Some m; Some sec |] -> h * 3600 + m * 60 + sec
    | _ -> 0

(*
 The dialer has no role field, so role comes from the CRM by name, on both
 name keys so "Last, First" and middle initials still match (about 97% do).
 The first role listed is the one shown. Anyone unmatched reads "unknown"
 rather than dropping off the board.
*)
let private rolesByName (users: Row array) =
    let roles = Dictionary<string, string>()
    for r in (if isNull users then [||] else users) |> Array.filter isObject do
        let raw = (text r "role_names").ToLowerInvariant()
        if raw <> "" then
            let primary = match raw.Split(',').[0].Trim() with "" -> "unknown" | role -> role
            for field in [ "name"; "full_name" ] do
                let name = text r field
                if name <> "" then
                    let full, loose = Cpa.nameKeys name
                    for key in [ full; loose ] do
                        if not (roles.ContainsKey key) then roles.[key] <- primary
    roles

let private statusOf (r: Row) = (text r "live_status").ToUpperInvariant()

// The phone on every call in progress, which the shell turns into leads with leadsByPhone
let incallPhones (live: Row array) =
    live
    |> Array.filter (fun r -> isObject r && statusOf r = "INCALL")
    |> Array.map (fun r -> text r "call_phone_number")
    |> Array.filter (fun p -> p <> "")
    |> Array.distinct
    |> Array.sort

let leadsPerPhone = LEADS_PER_PHONE

(*
 The board. users and leads may be null when those pulls failed; role and
 lead are nice to have and never take the board down. now is the shell's,
 this never reads a clock.
*)
let board (live: Row array) (users: Row array) (leads: Row array) (now: string) =
    let roles = rolesByName users

    // a phone can match several leads; the most recently created one wins
    let leadByPhone = Dictionary<string, string * string>()
    for r in (if isNull leads then [||] else leads) |> Array.filter isObject do
        let phone, created = rawText (get r "phone"), rawText (get r "date_created")
        if phone <> "" then
            match leadByPhone.TryGetValue phone with
            | true, (_, prev) when not (created > prev) -> ()
            | _ -> leadByPhone.[phone] <- (rawText (get r "lead_id"), created)

    let agents =
        live
        |> Array.filter isObject
        |> Array.map (fun r ->
            let status = statusOf r
            let name = match text r "agent_full_name" with "" -> "user " + pyStr (get r "user") | n -> n
            let full, loose = Cpa.nameKeys name
            let role =
                match roles.TryGetValue full with
                | true, role when role <> "" -> role
                | _ ->
                    match roles.TryGetValue loose with
                    | true, role when role <> "" -> role
                    | _ -> "unknown"
            let phone = if status = "INCALL" then text r "call_phone_number" else ""
            {| user_id = rawText (get r "user")
               name = name
               role = role
               status = status
               status_label =
                (match LABELS.TryGetValue status with
                 | true, label -> label
                 | _ -> if status = "" then "Unknown" else status)
               duration_sec = durationSeconds (get r "last_state_duration")
               extension = text r "extension"
               campaign = textOf (orElse (get r "campaign_id") (get r "campaign_campaign_name"))
               ingroup = text r "call_ingroup_group_name"
               calls_today = num r "calls_today"
               phone = phone
               lead_id =
                (match leadByPhone.TryGetValue phone with
                 | true, (lead, _) when phone <> "" -> lead
                 | _ -> "") |})
        |> List.ofArray
        |> List.sortWith (fun a b ->
            let rank (s: string) = match ORDER.TryGetValue s with | true, n -> n | _ -> 9
            match compare (rank a.status) (rank b.status) with
            | 0 -> compare b.duration_sec a.duration_sec
            | c -> c)
        |> Array.ofList

    let order = ResizeArray<string>()
    let counts = Dictionary<string, int>()
    for a in agents do
        if counts.ContainsKey a.status then counts.[a.status] <- counts.[a.status] + 1
        else
            order.Add a.status
            counts.[a.status] <- 1

    {| agents = agents
       counts = createObj (order |> Seq.map (fun s -> s, box counts.[s]))
       total = agents.Length
       generated_at = now
       demo = false |}
