"""Parse World Bank Pink Sheet monthly prices into a lead price series.

Usage:
    python -m core_pipeline.ingest_lead

Output: data/processed/lead_price_monthly.parquet with columns date, lead_usd_mt
"""

import re
from pathlib import Path

import pandas as pd

RAW = Path("data/raw/pink_sheet_monthly.xlsx")
OUT = Path("data/processed/lead_price_monthly.parquet")
SHEET = "Monthly Prices"
DATE_RE = re.compile(r"^(\d{4})M(\d{2})$")


def main() -> None:
    raw = pd.read_excel(RAW, sheet_name=SHEET, header=None)
    header_row = None
    for i in range(min(15, len(raw))):
        if (raw.iloc[i].astype(str).str.strip() == "Lead").any():
            header_row = i
            break
    if header_row is None:
        raise SystemExit("could not find a 'Lead' header in the first 15 rows")
    col = raw.iloc[header_row].astype(str).str.strip().tolist().index("Lead")

    dates = raw.iloc[:, 0].astype(str).str.strip()
    mask = dates.str.match(DATE_RE)
    sub = raw.loc[mask, [0, col]].copy()
    sub.columns = ["period", "lead_usd_mt"]
    sub["date"] = pd.to_datetime(sub["period"].str.replace("M", "-", regex=False), format="%Y-%m")
    sub["lead_usd_mt"] = pd.to_numeric(sub["lead_usd_mt"], errors="coerce")
    out = sub[["date", "lead_usd_mt"]].dropna().sort_values("date").reset_index(drop=True)
    out = out[out["date"] >= "2015-01-01"]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(OUT, index=False)
    print(f"{OUT}: {len(out)} rows, {out['date'].min():%Y-%m}..{out['date'].max():%Y-%m}, "
          f"last={out['lead_usd_mt'].iloc[-1]:.1f}")


if __name__ == "__main__":
    main()
