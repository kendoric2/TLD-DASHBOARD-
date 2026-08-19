#!/usr/bin/env python3
"""
Inbound vs outbound, per vendor (READ-ONLY).

The call log holds BOTH: ~91% outbound auto-dialling and ~9% inbound. Mixing them makes the
dispositions look like answering-machine noise, because that's what a dialer working a list
produces — it says nothing about the quality of what a vendor sent you.

This splits the log by direction so we can see, per vendor:
  • how many calls are inbound vs outbound
  • what the dispositions look like for EACH direction
  • how many are billable in each (i.e. which direction you're actually paying for)

That tells us what the Vendors tab should default to.

Usage:
  python3 sandbox/probes/probe_inbound.py [DAYS]      # default 1 (yesterday)
"""
import os
import sys
import time
import datetime
from collections import Counter, defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
import config  # noqa: E402

EP = "tldialer/tldialer_call_log"
DAYS = int(sys.argv[1]) if len(sys.argv) > 1 else 1
END = datetime.date.today() - datetime.timedelta(days=1)
START = END - datetime.timedelta(days=DAYS - 1)


def rows_of(resp):
    if isinstance(resp, list):
        return resp
    if isinstance(resp, dict):
        for k in ("results", "data", "rows", "records"):
            if isinstance(resp.get(k), list):
                return resp[k]
    return []


def num(v):
    try:
        return float(str(v).replace("$", "").replace(",", "").strip())
    except (TypeError, ValueError):
        return 0.0


def billable(r):
    return str(r.get("billable")).strip() in ("1", "1.0", "True", "true")


def main():
    if not config.have_creds():
        print("No credentials found. Run on the machine where .env is configured.")
        return

    t0 = time.time()
    rows = [r for r in rows_of(config.egress_get(EP, {
        "columns": ["call_date", "call_direction", "call_type", "status_name",
                    "vendor_description", "vendor_id", "agent_name", "billable", "cost"],
        "limit": 200000,
        "call_date": f"{START} 00:00:00", "call_date_end": f"{END} 23:59:59"},
        timeout=300)) if isinstance(r, dict)]
    print(f"\nINBOUND vs OUTBOUND   {START} .. {END}\n" + "=" * 74)
    print(f"pulled {len(rows):,} calls in {int((time.time()-t0)*1000):,} ms\n")
    if not rows:
        return

    inb = [r for r in rows if str(r.get("call_direction") or "").upper() == "INBOUND"]
    outb = [r for r in rows if str(r.get("call_direction") or "").upper() == "OUTBOUND"]
    print(f"  INBOUND  {len(inb):>8,}  ({len(inb)/len(rows)*100:4.1f}%)   "
          f"billable {sum(1 for r in inb if billable(r)):>6,}   "
          f"cost ${sum(num(r.get('cost')) for r in inb):>12,.2f}")
    print(f"  OUTBOUND {len(outb):>8,}  ({len(outb)/len(rows)*100:4.1f}%)   "
          f"billable {sum(1 for r in outb if billable(r)):>6,}   "
          f"cost ${sum(num(r.get('cost')) for r in outb):>12,.2f}")
    print("\n  ^ whichever direction carries the cost is the one you're being billed for")

    # ---- per vendor, split by direction ---------------------------------------------
    print("\nPER VENDOR\n" + "-" * 74)
    print(f"  {'VENDOR':<28}{'INBOUND':>9}{'OUTBOUND':>10}{'IN-BILL':>9}{'OUT-BILL':>10}")
    by = defaultdict(lambda: {"in": 0, "out": 0, "inb": 0, "outb": 0})
    for r in rows:
        v = by[str(r.get("vendor_description") or "(blank)")]
        if str(r.get("call_direction") or "").upper() == "INBOUND":
            v["in"] += 1
            v["inb"] += 1 if billable(r) else 0
        else:
            v["out"] += 1
            v["outb"] += 1 if billable(r) else 0
    for name, v in sorted(by.items(), key=lambda x: -(x[1]["in"] + x[1]["out"]))[:12]:
        print(f"  {name[:27]:<28}{v['in']:>9,}{v['out']:>10,}{v['inb']:>9,}{v['outb']:>10,}")

    # ---- dispositions, per direction -------------------------------------------------
    for label, subset in (("INBOUND", inb), ("OUTBOUND", outb)):
        if not subset:
            continue
        c = Counter(str(r.get("status_name") or "(blank)") for r in subset)
        print(f"\n{label} dispositions ({len(c)} distinct, {len(subset):,} calls)\n" + "-" * 74)
        for k, n in c.most_common(14):
            print(f"  {k[:40]:<42}{n:>8,}  ({n/len(subset)*100:4.1f}%)")

    # ---- what call_type tells us -----------------------------------------------------
    print("\nCALL TYPE (how the call arrived)\n" + "-" * 74)
    for label, subset in (("INBOUND", inb), ("OUTBOUND", outb)):
        c = Counter(str(r.get("call_type") or "(blank)") for r in subset)
        print(f"  {label}: {dict(c.most_common(6))}")

    print("\n" + "=" * 74)
    print("Read it like this:")
    print("  • If vendor leads arrive INBOUND, the tab should default to inbound only.")
    print("  • If vendors are dialled OUTBOUND, then outbound IS the vendor data and the")
    print("    answering-machine rate is a real quality signal, not noise.")
    print("  • Follow the billable/cost column — that's the direction you pay for.\n")


if __name__ == "__main__":
    main()
