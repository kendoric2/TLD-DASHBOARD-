"""Probe /api/egress/vendorperformance — columns, join keys, sample, date test.
Vendor-level aggregates (no customer PII). This is your Falcon view at the source.
Run: python3 sandbox/probes/probe_vendorperformance.py"""
import _probe_lib as p

p.survey("vendorperformance", sample=8, report_dates=True)
