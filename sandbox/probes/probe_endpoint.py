"""
Generic read-only probe for any egress endpoint — human-readable.
Shows columns + join keys + an aligned sample.

Usage:
    python3 sandbox/probes/probe_endpoint.py vendors
    python3 sandbox/probes/probe_endpoint.py report_cpa_agent
"""
import sys
import _probe_lib as p

ep = (sys.argv[1] if len(sys.argv) > 1 else "vendors").strip("/")

p.config.require_creds()
p.hr(f"/api/egress/{ep}")
p.show_columns(p.cols_of(ep))
print("\nsample (up to 5 rows):")
p.show_rows(p.pull(ep, 5), limit=5)
print("\nDone. Paste this back.")
