"""Probe /api/egress/leads — columns, join keys, PII-safe sample, date filter.
Run: python3 sandbox/probes/probe_leads.py"""
import _probe_lib as p

p.survey(
    "leads",
    sample_cols=["lead_id", "date_created", "date_converted", "vendor_id",
                 "status_name", "cost", "billable", "agent_name", "fronter_name",
                 "owner_name", "linked_lead_id", "policies_sold"],
    date_field="date_created",
    count_col="tql_cnt_lead_id",
)
