"""D6: EU member-state imports of CN 8507 10 20 / 8507 10 80 from Korea, China and World (Eurostat Comext).

Usage:
    python -m core_pipeline.ingest_comext
    python -m core_pipeline.ingest_comext --from-csv      # after a manual Easy Comext export

Primary route: Comext JSON-stat endpoint (statistics/1.0, order-free filters), one call per reporter.
Fallback: Easy Comext (DS-045409) manual export to data/raw/comext_850710.csv.

Output: data/processed/eu_import_monthly.parquet
    columns: date, reporter, partner, cn8, value_eur, qty_100kg, units
"""

import argparse
import time
from pathlib import Path

import pandas as pd
import requests

RAW = Path("data/raw/comext_850710.csv")
OUT = Path("data/processed/eu_import_monthly.parquet")
URL = "https://ec.europa.eu/eurostat/api/comext/dissemination/statistics/1.0/data/DS-045409"
EU27 = ["AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE", "IT",
        "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE"]
PARTNERS = ["KR", "CN", "WORLD"]
PRODUCTS = ["85071020", "85071080"]
INDICATORS = ["VALUE_IN_EUROS", "QUANTITY_IN_100KG", "SUPPLEMENTARY_QUANTITY"]


def jsonstat_to_df(js: dict) -> pd.DataFrame:
    dims = js["id"]
    cats = {d: list(js["dimension"][d]["category"]["index"].keys()) for d in dims}
    idx = pd.MultiIndex.from_product([cats[d] for d in dims], names=dims)
    n = 1
    for s in js["size"]:
        n *= s
    vals = js["value"]
    arr = [vals.get(str(i)) for i in range(n)]
    return pd.DataFrame({"value": arr}, index=idx).reset_index()


def fetch_reporter(rep: str, start: str) -> pd.DataFrame:
    params = [("format", "JSON"), ("lang", "EN"), ("freq", "M"), ("reporter", rep), ("flow", "1"),
              ("sinceTimePeriod", start)]
    params += [("partner", p) for p in PARTNERS]
    params += [("product", p) for p in PRODUCTS]
    params += [("indicators", i) for i in INDICATORS]
    r = requests.get(URL, params=params, timeout=180)
    if r.status_code != 200:
        print(f"  {rep}: {r.status_code} {r.text[:200]}")
        return pd.DataFrame()
    js = r.json()
    if "value" not in js or not js["value"]:
        print(f"  {rep}: no data")
        return pd.DataFrame()
    return jsonstat_to_df(js)


def fetch_all(start: str) -> pd.DataFrame:
    frames = []
    for rep in EU27:
        df = fetch_reporter(rep, start)
        if not df.empty:
            frames.append(df)
            print(f"  {rep}: {len(df)} cells")
        time.sleep(0.3)
    if not frames:
        raise SystemExit("comext: nothing fetched; use Easy Comext export and --from-csv")
    df = pd.concat(frames, ignore_index=True)
    RAW.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(RAW, index=False)
    return df


def normalise(df: pd.DataFrame) -> pd.DataFrame:
    cols = {c.lower(): c for c in df.columns}

    def pick(*names):
        for n in names:
            if n in cols:
                return cols[n]
        raise KeyError(f"none of {names} in {list(df.columns)}")

    c_rep, c_par, c_prod = pick("reporter"), pick("partner"), pick("product")
    c_ind = pick("indicators")
    c_time = pick("time", "time_period", "period")
    c_val = pick("value", "obs_value")
    d = df[[c_rep, c_par, c_prod, c_ind, c_time, c_val]].copy()
    d.columns = ["reporter", "partner", "cn8", "indicator", "period", "value"]
    d["date"] = pd.to_datetime(d["period"].astype(str).str[:7], format="%Y-%m")
    d["value"] = pd.to_numeric(d["value"], errors="coerce")
    d = d.dropna(subset=["value"])
    w = d.pivot_table(index=["date", "reporter", "partner", "cn8"], columns="indicator",
                      values="value", aggfunc="sum").reset_index()
    w = w.rename(columns={"VALUE_IN_EUROS": "value_eur", "QUANTITY_IN_100KG": "qty_100kg",
                          "SUPPLEMENTARY_QUANTITY": "units"})
    for c in ["value_eur", "qty_100kg", "units"]:
        if c not in w.columns:
            w[c] = 0.0
    w["cn8"] = w["cn8"].astype(str)
    return w[["date", "reporter", "partner", "cn8", "value_eur", "qty_100kg", "units"]].sort_values(
        ["reporter", "partner", "cn8", "date"]).reset_index(drop=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2018-01")
    ap.add_argument("--from-csv", action="store_true")
    args = ap.parse_args()
    df = pd.read_csv(RAW) if args.from_csv else fetch_all(args.start)
    out = normalise(df)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(OUT, index=False)
    print(f"{OUT}: {len(out)} rows, reporters={out['reporter'].nunique()}, partners={sorted(out['partner'].unique())}, "
          f"{out['date'].min():%Y-%m}..{out['date'].max():%Y-%m}, cn8={sorted(out['cn8'].unique())}")


if __name__ == "__main__":
    main()
