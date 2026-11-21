"""Extract the table of drug overdose deaths per year (2001-2021) from the NCHS Data Brief 457 PDF.

Source: Spencer MR, Miniño AM, Warner M. Drug overdose deaths in the United States, 2001–2021.
NCHS Data Brief, no 457. National Center for Health Statistics, 2022.
https://www.cdc.gov/nchs/products/databriefs/db457.htm

The PDF text loses the decimal point of the rates (6.8 is read as 68), so rates are divided by 10.

Inputs:
    data/raw/drug_overdose_us_2001_2021.pdf   (data table for Figure 1, first page)
Outputs:
    data/processed/drug_overdose_us_2001_2021.csv

Usage (from the repository root; needs the `pdftotext` command, from poppler):
    python src/extract_overdose_pdf.py
"""
import re
import subprocess
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PDF = ROOT / "data" / "raw" / "drug_overdose_us_2001_2021.pdf"
OUT = ROOT / "data" / "processed" / "drug_overdose_us_2001_2021.csv"

if __name__ == "__main__":
    text = subprocess.run(["pdftotext", "-layout", "-f", "1", "-l", "1", str(PDF), "-"],
                          capture_output=True, text=True, check=True).stdout
    number = lambda s: int(s.replace(",", ""))
    rows = []
    for line in text.splitlines():
        m = re.match(r"\s*(20\d\d)\s+([\d,]+)\s+(\d+)\s+([\d,]+)\s+(\d+)\s+([\d,]+)\s+(\d+)\s*$", line)
        if m:
            year, dt, rt, dm, rm, df, rf = m.groups()
            rows.append({"year": int(year),
                         "deaths_total": number(dt), "rate_total_per_100k": int(rt) / 10,
                         "deaths_male": number(dm), "rate_male_per_100k": int(rm) / 10,
                         "deaths_female": number(df), "rate_female_per_100k": int(rf) / 10})
    d = pd.DataFrame(rows)
    # Check: 21 years, and men + women = total
    assert len(d) == 21 and (d["deaths_male"] + d["deaths_female"] == d["deaths_total"]).all()
    d.to_csv(OUT, index=False)
    print(OUT.name, len(d), "rows")
