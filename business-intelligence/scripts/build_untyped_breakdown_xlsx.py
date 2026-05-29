#!/usr/bin/env python3
"""
Build a forwardable Excel breakdown of blank ("Untyped") appointment types
by clinician / calendar, straight from the warehouse.

Aggregates only (counts per clinician) - no patient PII. Safe to forward.

Usage:
    python3 scripts/build_untyped_breakdown_xlsx.py
"""
from __future__ import annotations

import subprocess
import json
from datetime import date
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

# Clinician code -> friendly name (from stg.appointments calendar-colour map).
CLINICIAN_NAMES = {
    "PCL": "Cheryl Long (director)",
    "PKN": "Kristy Ng",
    "PCN": "Claire Ng",
}

SQL = """
SELECT
  COALESCE(clinician_id, '(unmapped)')                            AS clinician_id,
  COALESCE(calendar_color, '(none)')                              AS calendar_color,
  COUNT(*)                                                        AS total_appts,
  COUNTIF(treatment_type = 'Untyped')                             AS untyped_appts,
  ROUND(100 * COUNTIF(treatment_type = 'Untyped') / COUNT(*), 1)  AS pct_untyped
FROM `goji-bi.stg.appointments`
WHERE appt_date >= '2026-01-01'
GROUP BY 1, 2
ORDER BY untyped_appts DESC
"""


def fetch_rows() -> list[dict]:
    out = subprocess.run(
        ["bq", "query", "--use_legacy_sql=false", "--format=json", SQL],
        check=True, capture_output=True, text=True,
    ).stdout
    return json.loads(out)


def build(rows: list[dict], dest: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Untyped by clinician"

    navy = "1F3864"
    light = "D9E1F2"
    grey = "808080"
    white_bold = Font(bold=True, color="FFFFFF")
    bold = Font(bold=True)
    center = Alignment(horizontal="center", vertical="center")
    left = Alignment(horizontal="left", vertical="center", wrap_text=True)
    thin = Side(style="thin", color="BFBFBF")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    # Title + context block
    ws["A1"] = "Goji Health - Appointments with no treatment type set"
    ws["A1"].font = Font(bold=True, size=14, color=navy)
    ws.merge_cells("A1:E1")
    ws["A2"] = (
        f"Source: Plato via goji-bi warehouse. Period: 2026 year-to-date. "
        f"Generated {date.today().isoformat()}."
    )
    ws["A3"] = (
        "\"Untyped\" = appointment booked without picking a type in Plato "
        "(the code_Bottom field is blank). These appointments are invisible to "
        "the treatment-mix chart. Lower % is better."
    )
    for r in (2, 3):
        ws[f"A{r}"].font = Font(italic=True, color=grey, size=10)
        ws[f"A{r}"].alignment = left
        ws.merge_cells(f"A{r}:E{r}")
    ws.row_dimensions[3].height = 30

    # Header row
    headers = ["Clinician", "Calendar", "Total appointments",
               "Untyped (no type)", "% untyped"]
    hrow = 5
    for c, h in enumerate(headers, start=1):
        cell = ws.cell(row=hrow, column=c, value=h)
        cell.font = white_bold
        cell.fill = PatternFill("solid", fgColor=navy)
        cell.alignment = center
        cell.border = border

    # Data rows
    tot_total = tot_untyped = 0
    r = hrow + 1
    for row in rows:
        code = row["clinician_id"]
        name = CLINICIAN_NAMES.get(code, f"Unknown calendar ({code})")
        total = int(row["total_appts"])
        untyped = int(row["untyped_appts"])
        pct = float(row["pct_untyped"])
        tot_total += total
        tot_untyped += untyped
        values = [name, row["calendar_color"], total, untyped, pct / 100]
        for c, v in enumerate(values, start=1):
            cell = ws.cell(row=r, column=c, value=v)
            cell.border = border
            cell.alignment = left if c == 1 else center
        ws.cell(row=r, column=5).number_format = "0.0%"
        r += 1

    # Totals row
    for c in range(1, 6):
        cell = ws.cell(row=r, column=c)
        cell.fill = PatternFill("solid", fgColor=light)
        cell.font = bold
        cell.border = border
        cell.alignment = left if c == 1 else center
    ws.cell(row=r, column=1, value="All clinicians")
    ws.cell(row=r, column=3, value=tot_total)
    ws.cell(row=r, column=4, value=tot_untyped)
    pct_cell = ws.cell(row=r, column=5,
                       value=(tot_untyped / tot_total) if tot_total else 0)
    pct_cell.number_format = "0.0%"

    widths = [26, 12, 18, 18, 12]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A6"

    wb.save(dest)


def main() -> None:
    rows = fetch_rows()
    dest = Path(__file__).resolve().parents[1] / "Goji - untyped appointments by clinician (2026 YTD).xlsx"
    build(rows, dest)
    print(f"wrote {dest}")


if __name__ == "__main__":
    main()
