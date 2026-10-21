module Tld.Queries

// The request bodies sent to TLD's egress api. Pure data: the shell sends
// them, this only says what they are. Shared, so a future report asking for
// the same policies asks for them the same way.
//
// Ported from the TLD dashboard's egress_payloads.json and _payload. Only the
// queries still in use came across; the json also held policies_count,
// policies_by_carrier, billable_leads_count and agent_policies, which nothing
// had called for some time.

open Fable.Core.JsInterop

(*-------- This is critical --------*)
(*
 TLD's date rule for the policies endpoint and the cost report: BOTH date /
 date_end AND date_sold / date_sold_end, full day bounds, YYYY-MM-DD HH:MM:SS.
 Either pair alone returns a different set, which is how the dashboard once
 disagreed with TLD's own screens. The leads endpoint is the exception and is
 filtered on date_created instead, see the queries that need it.
*)
let canonicalDates (start: string) (finish: string) =
    let s0, e1 = start + " 00:00:00", finish + " 23:59:59"
    [ "date", box s0; "date_end", box e1; "date_sold", box s0; "date_sold_end", box e1 ]

let private query (endpoint: string) (fields: (string * obj) list) =
    {| endpoint = endpoint; body = createObj fields |}

// Every policy in the range, one row each, with what the Dashboard tab counts
let policies (start: string) (finish: string) =
    query
        "policies"
        ([ "columns",
           box [| "policy_id"; "lead_id"; "date_sold"; "carrier_name"; "fronter_id"; "fronter_name"
                  "stage"; "agent_name"; "commission_paid"; "commission_paid_fronter"; "lead_state"
                  "status_name" |]
           "limit", box 200000 ]
         @ canonicalDates start finish)

(*
 Average premium across GTL and Manhattan Life together. Both carry a premium
 on every policy; the other carriers almost never do (2 of 198 UHC policies in
 October), so they stay out rather than drag the average toward zero.
*)
let averagePremium (start: string) (finish: string) =
    query
        "policies"
        ([ "carrier", box [| "GTL"; "MANHATTAN" |]
           "aggregates", box true
           "aggregate", box true
           "columns", box [| "tql_avg_premium" |] ]
         @ canonicalDates start finish)

(*
 TLD's cost report: spend, sales, CPA and billable calls per agent, with its
 own totals row. One org wide call covers Total Spend, Blended CPA, Billable
 Calls and Conversion Rate, so none of them needs a second ~30 second report.
*)
let costReport (start: string) (finish: string) =
    query
        "report_cpa_agent"
        ([ "columns", box [| "agent"; "agent_id"; "sales"; "costs_all"; "cpa_cost_calls_all_by_sales"; "calls_billable" |]
           "limit", box 1000 ]
         @ canonicalDates start finish)

(*=======================================================
        VENDORS
========================================================*)

// TLD's dialer call log. The tldialer/ namespace is required; the bare name does not reach it.
let CALL_LOG = "tldialer/tldialer_call_log"

let private callDates (start: string) (finish: string) =
    [ "call_date", box (start + " 00:00:00"); "call_date_end", box (finish + " 23:59:59") ]

let private optional (key: string) (value: string) =
    if System.String.IsNullOrEmpty value then [] else [ key, box value ]

// Every vendor with its price. Its status flag is unreliable, so nothing ranks by it.
let vendorList () =
    query "vendors" [ "columns", box [| "vendor_id"; "name"; "description"; "price"; "price_inbound"; "status_name" |]; "limit", box 500 ]

(*
 Leads are TLD's exception to the date rule: the leads endpoint ignores date
 and date_sold and returns the whole table, so it is filtered on date_created.
*)
let leadsCreated (start: string) (finish: string) (vendorId: string) =
    query
        "leads"
        ([ "columns", box [| "lead_id"; "vendor_id"; "billable"; "converted"; "policies_sold" |]
           "date_created", box (start + " 00:00:00")
           "date_created_end", box (finish + " 23:59:59")
           "limit", box 200000 ]
         @ optional "vendor_id" vendorId)

// Every lead created in the range with its customer state, for the state x vendor report
let leadsCreatedByState (start: string) (finish: string) =
    query
        "leads"
        [ "columns", box [| "lead_id"; "vendor_id"; "state"; "billable"; "policies_sold" |]
          "date_created", box (start + " 00:00:00")
          "date_created_end", box (finish + " 23:59:59")
          "limit", box 200000 ]

// Leads created in the range with their phone, for the vendor export's Sold Policies sheet
let leadsCreatedWithPhone (start: string) (finish: string) (vendorId: string) =
    query
        "leads"
        ([ "columns", box [| "lead_id"; "phone"; "policies_sold" |]
           "date_created", box (start + " 00:00:00")
           "date_created_end", box (finish + " 23:59:59")
           "limit", box 200000 ]
         @ optional "vendor_id" vendorId)

// Sold policies on a batch of leads, with the date sold
let soldPoliciesForLeads (leadIds: string array) =
    query "policies" [ "columns", box [| "policy_id"; "lead_id"; "date_sold"; "stage" |]; "lead_id", box leadIds; "limit", box 20000 ]

// The cost report narrowed to one vendor, or every vendor. costs_all honors vendor_id.
let vendorCost (start: string) (finish: string) (vendorId: string) =
    query
        "report_cpa_agent"
        ([ "columns", box [| "sales"; "costs_all"; "calls_billable" |]; "limit", box 2000 ]
         @ canonicalDates start finish
         @ optional "vendor_id" vendorId)

(*
 Every billed call. Billing is entirely inbound. billable is asked for here,
 but Tld.Vendors filters on it again, because TLD has silently ignored filters
 before and the answer must be right either way.
*)
let billedCalls (start: string) (finish: string) (vendorId: string) =
    query
        CALL_LOG
        ([ "columns",
           box [| "call_date"; "call_direction"; "status_name"; "agent_name"; "vendor_id"; "vendor_description"
                  "lead_vendor_lead_code"; "lead_id"; "billable"; "cost"; "duration_call"; "sec_talk" |]
           "limit", box 200000
           "billable", box 1
           "call_direction", box "INBOUND" ]
         @ callDates start finish
         @ optional "vendor_id" vendorId)

// One day of calls, for the disposition breakdown. direction "" means every direction.
let callsOnDay (day: string) (vendorId: string) (direction: string) =
    query
        CALL_LOG
        ([ "columns", box [| "status_name"; "status"; "did_description" |]; "limit", box 200000 ]
         @ callDates day day
         @ optional "vendor_id" vendorId
         @ optional "call_direction" (if isNull direction then "" else direction.ToUpperInvariant()))

(*
 A plain count of calls. TLD's group_by is broken on the call log (it folds
 everything into one mislabelled bucket) but its plain counts are exact, so
 this is what the day by day breakdown is checked against.
*)
let callCount (start: string) (finish: string) (vendorId: string) (direction: string) =
    query
        CALL_LOG
        ([ "aggregates", box true; "aggregate", box true; "columns", box [| "tql_cnt_call_log_id" |] ]
         @ callDates start finish
         @ optional "vendor_id" vendorId
         @ optional "call_direction" (if isNull direction then "" else direction.ToUpperInvariant()))

(*=======================================================
        LIVE AGENTS AND AGENT DETAIL
========================================================*)

(*
 The dialer's live board. Named tldialer_live_agents, not vicidial_live_agents,
 which this key cannot reach. Only people logged in right now appear.
*)
let liveAgents () =
    query
        "tldialer/tldialer_live_agents"
        [ "columns",
          box [| "user"; "agent_full_name"; "live_status"; "last_state_duration"; "extension"; "campaign_id"
                 "campaign_campaign_name"; "call_ingroup_group_name"; "calls_today"; "call_phone_number" |]
          "limit", box 1000 ]

// CRM users and their roles. Never more columns than these: the table also holds credentials
let crmUsers () =
    query "users" [ "columns", box [| "name"; "full_name"; "role_names" |]; "limit", box 5000 ]

// Leads for a batch of phone numbers in one call; the leads endpoint takes phone as a list
let leadsByPhone (phones: string array) (perPhone: int) =
    query "leads" [ "columns", box [| "lead_id"; "phone"; "date_created" |]; "phone", box phones; "limit", box (phones.Length * perPhone) ]

(*
 Leads that converted around the range, for their SEP. The leads endpoint
 ignores a lead_id filter but honors date_converted, and padding 3 days each
 side covers every policy sold in the range: about 900 rows in half a second,
 against 188k rows and 93% coverage filtering on date_created.
*)
let convertedLeads (start: string) (finish: string) =
    let pad (iso: string) (days: float) =
        Dates.parseIso iso |> Option.map (fun d -> Dates.iso (d.AddDays days)) |> Option.defaultValue iso
    query
        "leads"
        [ "columns", box [| "lead_id"; "sep" |]
          "date_converted", box (pad start -3.0 + " 00:00:00")
          "date_converted_end", box (pad finish 3.0 + " 23:59:59")
          "limit", box 200000 ]

// One person's calls. The call log honors agent_name, so this stays small
let agentCalls (start: string) (finish: string) (agentName: string) =
    query
        CALL_LOG
        ([ "columns", box [| "status_name"; "status"; "agent_name"; "sec_talk" |]
           "agent_name", box agentName
           "limit", box 200000 ]
         @ callDates start finish)

(*=======================================================
        TRANSFER CHECK
========================================================*)

// Every lead on a batch of phones, with the lead each is linked to
let leadsForPhones (phones: string array) =
    query
        "leads"
        [ "columns", box [| "lead_id"; "phone"; "date_created"; "linked_lead_id" |]
          "phone", box phones
          "limit", box (phones.Length * 50) ]

// Policies created in the range with the lead they are linked to, for links that point back
let policiesCreatedLinks (start: string) (finish: string) =
    query
        "policies"
        [ "columns", box [| "lead_id"; "lead_linked_lead_id" |]
          "limit", box 200000
          "date_created", box (start + " 00:00:00")
          "date_created_end", box (finish + " 23:59:59") ]

// Inbound calls from a batch of phones; the call log takes phone_number as a list
let inboundCalls (phones: string array) (start: string) (finish: string) =
    query
        CALL_LOG
        ([ "columns",
           box [| "call_date"; "phone_number"; "agent_name"; "status_name"; "vendor_description"; "did_description"
                  "lead_vendor_lead_code" |]
           "call_direction", box "INBOUND"
           "phone_number", box phones
           "limit", box 50000 ]
         @ callDates start finish)

// Just when each phone called in, for timing the fronters' own list
let inboundCallTimes (phones: string array) (start: string) (finish: string) =
    query
        CALL_LOG
        ([ "columns", box [| "call_date"; "phone_number" |]
           "call_direction", box "INBOUND"
           "phone_number", box phones
           "limit", box 50000 ]
         @ callDates start finish)

// Every policy ever written on a batch of leads, no date filter
let policiesForLeads (leadIds: string array) =
    query
        "policies"
        [ "columns",
          box [| "policy_id"; "lead_id"; "date_created"; "date_sold"; "status_name"; "carrier_name"; "agent_name"
                 "verified"; "verifier_name" |]
          "lead_id", box leadIds
          "limit", box 20000 ]

// One row per policy with the plan, for Agent Detail
let policyDetail (start: string) (finish: string) =
    query
        "policies"
        ([ "columns",
           box [| "policy_id"; "lead_id"; "date_sold"; "agent_name"; "fronter_name"; "carrier_name"
                  "product_plan_name"; "product_name"; "status_name"; "stage"; "lead_state" |]
           "limit", box 200000 ]
         @ canonicalDates start finish)
