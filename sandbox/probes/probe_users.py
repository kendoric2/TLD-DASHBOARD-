"""Probe /api/egress/users — columns, join keys, PII-safe sample (staff only).
Run: python3 sandbox/probes/probe_users.py"""
import _probe_lib as p

p.survey("users", sample_cols=["id", "full_name", "status_id", "status"], sample=5)
