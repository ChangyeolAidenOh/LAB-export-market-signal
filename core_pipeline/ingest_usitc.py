"""Parse a USITC DataWeb export (General Imports, HTS 8507.10, monthly, all countries)
into a long-format parquet.

Usage:
    python -m core_pipeline.ingest_usitc
    python -m core_pipeline.ingest_usitc --src data/raw/usitc_import_850710.xlsx

Output columns: date, origin, hts10, value_usd, qty_units, qty_suppressed
"""

import argparse
from pathlib import Path

import pandas as pd

RAW = Path("data/raw/usitc_import_850710.xlsx")
OUT = Path("data/processed/us_import_monthly.parquet")

MONTHS = ["January", "February", "March", "April", "May", "June",
          "July", "August", "September", "October", "November", "December"]
SHEET_VALUE = "General Customs Value"
SHEET_QTY = "General 1st Unit of Qty"


def read_sheet(src: Path, sheet: str) -> pd.DataFrame:
    df = pd.read_excel(src, sheet_name=sheet, header=2)
    df = df[df["Data Type"].astype(str).str.startswith("General")].copy()
    df["Year"] = df["Year"].astype(int)
    df["HTS Number"] = pd.to_numeric(df["HTS Number"], errors="coerce").astype("Int64").astype(str).str.zfill(10)
    return df


def to_long(df: pd.DataFrame, value_name: str, cols: list[str]) -> pd.DataFrame:
    long = df.melt(id_vars=["Country", "Year", "HTS Number"], value_vars=cols,
                   var_name="month", value_name=value_name)
    long["month"] = long["month"].str.replace("_Suppressed", "", regex=False)
    long["date"] = pd.to_datetime(long["Year"].astype(str) + "-" + long["month"], format="%Y-%B")
    long[value_name] = pd.to_numeric(long[value_name], errors="coerce").fillna(0)
    return long.drop(columns=["Year", "month"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(RAW))
    args = ap.parse_args()
    src = Path(args.src)

    val = to_long(read_sheet(src, SHEET_VALUE), "value_usd", MONTHS)
    qdf = read_sheet(src, SHEET_QTY)
    qty = to_long(qdf, "qty_units", MONTHS)
    sup_cols = [f"{m}_Suppressed" for m in MONTHS if f"{m}_Suppressed" in qdf.columns]
    sup = to_long(qdf, "qty_suppressed", sup_cols) if sup_cols else None

    keys = ["Country", "HTS Number", "date"]
    out = val.merge(qty, on=keys, how="outer")
    if sup is not None:
        out = out.merge(sup, on=keys, how="left")
    else:
        out["qty_suppressed"] = 0
    out = out.rename(columns={"Country": "origin", "HTS Number": "hts10"})
    out["qty_suppressed"] = out["qty_suppressed"].fillna(0).astype(int)

    last = out.loc[out["value_usd"] > 0, "date"].max()
    out = out[out["date"] <= last]
    out = out.sort_values(["origin", "hts10", "date"]).reset_index(drop=True)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(OUT, index=False)
    print(f"{OUT}: {len(out)} rows, {out['origin'].nunique()} origins, "
          f"hts10={sorted(out['hts10'].unique())}, {out['date'].min():%Y-%m}..{out['date'].max():%Y-%m}")
    n_sup = int((out["qty_suppressed"] > 0).sum())
    if n_sup:
        print(f"suppressed qty cells: {n_sup}")


if __name__ == "__main__":
    main()
