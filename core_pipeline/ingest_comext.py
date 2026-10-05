"""D6: EU member-state imports of CN 8507 10 20 / 8507 10 80 from Korea, China and World (Eurostat Comext).

Usage:
    python -m core_pipeline.ingest_comext
    python -m core_pipeline.ingest_comext --start 2018-01

Uses the Comext SDMX 2.1 REST endpoint (no account). If the endpoint rejects the query,
export the same selection manually from Easy Comext (dataset DS-045409) to
data/raw/comext_850710.csv and run with --from-csv.

Output: data/processed/eu_import_monthly.parquet
    columns: date, reporter, partner, cn8, value_eur, qty_100kg, units
"""

import argparse
import io
from pathlib import Path

import pandas as pd
import requests

RAW = Path("data/raw/comext_850710.csv")
OUT = Path("data/processed/eu_import_monthly.parquet")
BASE = "https://ec.europa.eu/eurostat/api/comext/dissemination/sdmx/2.1/data/DS-045409"
EU27 = ["AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "EL", "HU", "IE", "IT",
        "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE"]
PARTNERS = ["KR", "CN", "WORLD"]
PRODUCTS = ["85071020", "85071080"]
INDICATORS = ["VALUE_IN_EUROS", "QUANTITY_IN_100KG", "SUPPLEMENTARY_QUANTITY"]


def fetch(start: str, end: str) -> pd.DataFrame:
    key = ".".join(["M", "+".join(EU27), "+".join(PARTNERS), "+".join(PRODUCTS), "1", "+".join(INDICATORS)])
    url = f"{BASE}/{key}"
    r = requests.get(url, params={"startPeriod": start, "endPeriod": end, "format": "csvdata"}, timeout=120)
    if r.status_code != 200:
        raise SystemExit(f"comext {r.status_code}: {r.text[:300]}")
    df = pd.read_csv(io.StringIO(r.text))
    RAW.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(RAW, index=False)
    return df


def normalise(df: pd.DataFrame) -> pd.DataFrame:
    cols = {c.lower(): c for c in df.columns}
    def pick(*names):
        for n in names:
            if n in cols:
                return cols[n]
        raise KeyError(names)
    c_rep, c_par, c_prod = pick("reporter"), pick("partner"), pick("product")
    c_ind, c_time, c_val = pick("indicators"), pick("time_period", "period"), pick("obs_value", "value")
    d = df[[c_rep, c_par, c_prod, c_ind, c_time, c_val]].copy()
    d.columns = ["reporter", "partner", "cn8", "indicator", "period", "value"]
    d["date"] = pd.to_datetime(d["period"].astype(str).str[:7], format="%Y-%m")
    d["value"] = pd.to_numeric(d["value"], errors="coerce").fillna(0)
    w = d.pivot_table(index=["date", "reporter", "partner", "cn8"], columns="indicator", values="value", aggfunc="sum").reset_index()
    w = w.rename(columns={"VALUE_IN_EUROS": "value_eur", "QUANTITY_IN_100KG": "qty_100kg", "SUPPLEMENTARY_QUANTITY": "units"})
    for c in ["value_eur", "qty_100kg", "units"]:
        if c not in w.columns:
            w[c] = 0.0
    w["cn8"] = w["cn8"].astype(str)
    return w[["date", "reporter", "partner", "cn8", "value_eur", "qty_100kg", "units"]].sort_values(["reporter", "partner", "cn8", "date"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2018-01")
    ap.add_argument("--end", default="2026-12")
    ap.add_argument("--from-csv", action="store_true")
    args = ap.parse_args()
    df = pd.read_csv(RAW) if args.from_csv else fetch(args.start, args.end)
    out = normalise(df)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(OUT, index=False)
    print(f"{OUT}: {len(out)} rows, reporters={out['reporter'].nunique()}, "
          f"{out['date'].min():%Y-%m}..{out['date'].max():%Y-%m}, cn8={sorted(out['cn8'].unique())}")


if __name__ == "__main__":
    main()
