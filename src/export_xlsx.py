"""
Excel export for the Agent Detail view.

Builds an audit-ready .xlsx in memory: a header block naming the person, the exact date
range, when it was generated and the closed/enrolled/total summary, then the same eight
columns shown on screen. Nothing is written to disk — the file streams straight to the
browser.
"""
import io
import datetime

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

NAVY = "182A54"
GREEN = "00A248"
LINE = "D6DEE8"

# Exactly the columns shown in the Agent Detail table: (header, row key, width)
COLUMNS = [
    ("Date Sold", "date_sold", 13),
    ("Lead ID",   "lead_id",   14),
    ("Role",      "role",      11),
    ("Agent",     "agent",     26),
    ("Enroller",  "enroller",  26),
    ("Carrier",   "carrier",   16),
    ("Plan",      "plan",      18),
    ("SEP",       "sep",        9),
]


def sort_rows(rows, key="date_sold", desc=True):
    """Same ordering rule the on-screen table uses: blanks always sink to the bottom,
    whichever direction the rest is sorted."""
    keys = {c[1] for c in COLUMNS}
    if key not in keys:
        key = "date_sold"
    filled = [r for r in rows if str(r.get(key) or "").strip()]
    blank = [r for r in rows if not str(r.get(key) or "").strip()]
    if key == "lead_id":
        filled.sort(key=lambda r: float(str(r.get(key) or 0) or 0), reverse=desc)
    else:
        filled.sort(key=lambda r: str(r.get(key) or "").lower(), reverse=desc)
    return filled + blank


def safe_name(s):
    """'Powers, Tony' -> 'Powers-Tony' so filenames stay clean and unambiguous."""
    out = "".join(ch if ch.isalnum() else "-" for ch in str(s or "").strip())
    while "--" in out:
        out = out.replace("--", "-")
    return out.strip("-") or "agent"


def build(agent, start, end, range_label, summary, rows):
    """Return (BytesIO, filename) for the given person's deals."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Agent Detail"

    title_f = Font(name="Calibri", size=15, bold=True, color=NAVY)
    lbl_f = Font(name="Calibri", size=10, bold=True, color="6B7C93")
    val_f = Font(name="Calibri", size=10, color="1E2A44")
    head_f = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
    head_fill = PatternFill("solid", fgColor=NAVY)
    thin = Side(style="thin", color=LINE)
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    # --- header block: what this file is, who it's about, and when it was produced ---
    ws["A1"] = "Agent Detail — Audit Export"
    ws["A1"].font = title_f
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(COLUMNS))

    meta = [
        ("Agent", agent),
        ("Date range", f"{range_label}   ({start} to {end})"),
        ("Generated", datetime.datetime.now().strftime("%Y-%m-%d %H:%M")),
        ("Summary", f"Closed {summary.get('closed', 0)}   ·   "
                    f"Enrolled {summary.get('enrolled', 0)}   ·   "
                    f"Total {summary.get('total', 0)}"),
    ]
    r = 2
    for label, value in meta:
        ws.cell(row=r, column=1, value=label).font = lbl_f
        c = ws.cell(row=r, column=2, value=value)
        c.font = val_f
        ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=len(COLUMNS))
        r += 1

    ws.cell(row=r, column=1, value="Source: TLDCRM (read-only). "
                                   "Blank enroller = the agent enrolled the deal themselves.").font = lbl_f
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=len(COLUMNS))
    head_row = r + 2

    # --- table ---
    for i, (header, _key, width) in enumerate(COLUMNS, start=1):
        c = ws.cell(row=head_row, column=i, value=header)
        c.font = head_f
        c.fill = head_fill
        c.alignment = Alignment(horizontal="left", vertical="center")
        c.border = border
        ws.column_dimensions[get_column_letter(i)].width = width
    ws.row_dimensions[head_row].height = 20

    for n, row in enumerate(rows, start=head_row + 1):
        for i, (_header, key, _w) in enumerate(COLUMNS, start=1):
            val = row.get(key)
            val = "—" if val in (None, "") else val
            if key == "lead_id":
                try:
                    val = int(str(val))          # keep lead ids numeric for sorting in Excel
                except (TypeError, ValueError):
                    pass
            c = ws.cell(row=n, column=i, value=val)
            c.font = val_f
            c.border = border
            c.alignment = Alignment(horizontal="left")

    if not rows:
        c = ws.cell(row=head_row + 1, column=1, value="No deals for this person in this range.")
        c.font = val_f
        ws.merge_cells(start_row=head_row + 1, start_column=1,
                       end_row=head_row + 1, end_column=len(COLUMNS))

    ws.freeze_panes = ws.cell(row=head_row + 1, column=1)   # keep headers visible when scrolling
    ws.auto_filter.ref = (f"A{head_row}:"
                          f"{get_column_letter(len(COLUMNS))}{head_row + max(len(rows), 1)}")

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    fname = f"AgentDetail_{safe_name(agent)}_{start}_{end}.xlsx"
    return buf, fname
