"""Probe /api/egress/vendors — human-readable. Lists every vendor (id + name).
Run: python3 sandbox/probes/probe_vendors.py"""
import _probe_lib as p

p.config.require_creds()
p.hr("/api/egress/vendors")
p.show_columns(p.cols_of("vendors"))

rows = p.pull("vendors", 500)
print("\nvendors (id  →  name):")
if isinstance(rows, list):
    for v in sorted(rows, key=lambda x: str(x.get("name") or "")):
        vid = v.get("vendor_id") or v.get("id")
        name = v.get("name") or v.get("vendor_name") or v.get("vendor") or "?"
        print(f"    {str(vid).ljust(8)} {name}")
    print(f"\n  {len(rows)} vendors total.")
else:
    print("  ", rows)
print("\nDone. Paste this back.")
