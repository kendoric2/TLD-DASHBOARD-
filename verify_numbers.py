"""
Verify the live numbers filter correctly by date (read-only, GET + JSON body).

Run on your Mac:
    cd ~/Documents/TLDDASHBOARD
    python3 verify_numbers.py

If the date filter works, the counts GROW with the range
(today < this week < this month < this quarter) — they should NOT all be the
same ~all-time number. Then compare 'this_month' policies to what TLD shows you.
"""
import config
import tldcrm_client as t

config.require_creds()
c = t.TLDCRMClient(config.TLD_BASE_URL, config.TLD_API_ID, config.TLD_API_KEY)


def count(query, s, e):
    try:
        return f"{t._first_num(c.run(query, s, e)):,}"
    except Exception as ex:
        return f"ERR {type(ex).__name__}: {str(ex)[:60]}"


print(f"{'range':13}{'policies':>11}{'billable_leads':>17}   window")
print("-" * 62)
for rk in ["today", "this_week", "this_month", "last_month", "this_quarter"]:
    s, e = t.date_range_for(rk)
    print(f"{rk:13}{count('policies_count', s, e):>11}"
          f"{count('billable_leads_count', s, e):>17}   {t._us(s)} .. {t._us(e)}")

print("\nExpected: numbers grow with the range. If they're all the same big number,")
print("the date filter still isn't biting. Compare 'this_month' to TLD's own total.")
