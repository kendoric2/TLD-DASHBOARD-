#!/usr/bin/env python3
"""
SEP join — CORRECTED verification (READ-ONLY).

Rounds 1-2 established:
  • the leads endpoint ignores a lead_id filter (string OR integer, single OR list)
  • pulling a 180-day lead window works but is 188k rows / 8s and still only ~93% coverage
  • filtering leads by `date_converted` over the SALE window returned ~the right count in 0.6s

Round 2's verdict was wrong: it compared the date_converted result against 5 sample ids
instead of the full set, so a working filter looked like a failure. This probe does the
check properly — it measures what fraction of the sold policies' lead_ids are actually
covered by a date_converted pull, and tries a small padding either side.

Usage:
  python3 sandbox/probes/probe_lead_join2.py [DAYS_OF_SALES]   # default 7
"""
import os
import sys
import time
import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
import config  # noqa: E402

SALE_DAYS = int(sys.argv[1]) if len(sys.argv) > 1 else 7
TODAY = datetime.date.today()
SALE_START = TODAY - datetime.timedelta(days=SALE_DAYS)


def rows_of(resp):
    if isinstance(resp, list):
        return resp
    if isinstance(resp, dict):
        for k in ("results", "data", "rows", "records"):
            if isinstance(resp.get(k), list):
                return resp[k]
    return []


def converted_leads(pad_days):
    """Leads whose date_converted falls in the sale window, padded by N days each side."""
    a = SALE_START - datetime.timedelta(days=pad_days)
    b = TODAY + datetime.timedelta(days=pad_days)
    t0 = time.time()
    rows = rows_of(config.egress_get("leads", {
        "columns": ["lead_id", "sep", "date_converted"],
        "date_converted": f"{a} 00:00:00", "date_converted_end": f"{b} 23:59:59",
        "limit": 200000}, timeout=180))
    ms = int((time.time() - t0) * 1000)
    by_id = {str(r["lead_id"]): r for r in rows
             if isinstance(r, dict) and r.get("lead_id")}
    return by_id, len(rows), ms


def main():
    if not config.have_creds():
        print("No credentials found. Run on the machine where .env is configured.")
        return

    s0, e1 = f"{SALE_START} 00:00:00", f"{TODAY} 23:59:59"
    print(f"\nSEP JOIN — date_converted verification   sales {SALE_START} .. {TODAY}\n" + "=" * 70)

    pol = rows_of(config.egress_get("policies", {
        "columns": ["policy_id", "lead_id", "date_sold"], "sold": 1,
        "date": s0, "date_end": e1, "date_sold": s0, "date_sold_end": e1,
        "limit": 20000}, timeout=120))
    pol = [r for r in pol if isinstance(r, dict) and r.get("lead_id")]
    need = {str(r["lead_id"]) for r in pol}
    print(f"policies sold: {len(pol):,}    distinct lead_ids to resolve: {len(need):,}\n")

    print(f"{'padding':>9}{'leads pulled':>14}{'time':>9}{'COVERAGE':>11}{'with SEP':>11}")
    print("-" * 70)
    best = None
    for pad in (0, 1, 3, 7):
        by_id, n, ms = converted_leads(pad)
        matched = need & set(by_id)
        cov = len(matched) / len(need) * 100 if need else 0
        sep_n = sum(1 for k in matched if by_id[k].get("sep"))
        sep_pct = sep_n / len(matched) * 100 if matched else 0
        print(f"{pad:>7}d{n:>14,}{ms / 1000:>8.1f}s{cov:>10.1f}%{sep_pct:>10.1f}%")
        if best is None or cov > best[1]:
            best = (pad, cov, by_id)

    pad, cov, by_id = best
    print("-" * 70)
    print(f"\nbest: {pad}-day padding -> {cov:.1f}% of sold policies get their lead (and SEP)")

    missing = [k for k in need if k not in by_id]
    if missing:
        print(f"\n{len(missing)} lead(s) not covered — sample: {missing[:5]}")
        print("(these converted outside the window; we'd show SEP as '—' for them)")

    print("\nSample joined rows (what the Agent Detail table would show):")
    shown = 0
    for r in pol:
        lid = str(r["lead_id"])
        if lid in by_id and shown < 8:
            print(f"   lead {lid}   sold {str(r.get('date_sold'))[:10]}   sep={by_id[lid].get('sep') or '—'}")
            shown += 1

    print("\n" + "=" * 70)
    if cov >= 97:
        print(f"VERDICT: use date_converted with {pad}-day padding. One extra fast call per view.")
    elif cov >= 85:
        print(f"VERDICT: date_converted covers {cov:.0f}%. Good enough — uncovered rows show '—'.")
    else:
        print(f"VERDICT: only {cov:.0f}% covered; we'd need the wider date_created window instead.")
    print()


if __name__ == "__main__":
    main()
