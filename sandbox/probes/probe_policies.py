"""Probe /api/egress/policies — columns, join keys, PII-safe sample, date filter.
Run: python3 sandbox/probes/probe_policies.py"""
import _probe_lib as p

p.survey(
    "policies",
    sample_cols=["policy_id", "date_sold", "agent_name", "carrier_name",
                 "product", "premium", "status"],
    date_field="date_sold",
    count_col="tql_cnt_policy_id",
)
