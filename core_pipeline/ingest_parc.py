"""D7: passenger car fleet by age, EU member states (Eurostat road_eqs_carage).

Usage:
    python -m core_pipeline.ingest_parc

Output: data/processed/eu_car_parc.parquet
    columns: geo, year, cars_total, cars_age_ge10, share_age_ge10
"""

from pathlib import Path

import pandas as pd
import requests

OUT = Path("data/processed/eu_car_parc.parquet")
URL = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/road_eqs_carage"


def jsonstat_to_df(js: dict) -> pd.DataFrame:
    dims = js["id"]
    sizes = js["size"]
    cats = {d: list(js["dimension"][d]["category"]["index"].keys()) for d in dims}
    idx = pd.MultiIndex.from_product([cats[d] for d in dims], names=dims)
    vals = js["value"]
    n = 1
    for s in sizes:
        n *= s
    arr = [vals.get(str(i)) for i in range(n)]
    return pd.DataFrame({"value": arr}, index=idx).reset_index()


def main() -> None:
    r = requests.get(URL, params={"format": "JSON", "lang": "EN", "unit": "NR"}, timeout=120)
    if r.status_code != 200:
        raise SystemExit(f"eurostat {r.status_code}: {r.text[:300]}")
    df = jsonstat_to_df(r.json())
    df = df.dropna(subset=["value"])
    df["year"] = df["time"].astype(int)
    age_col = "age"
    ages = sorted(df[age_col].unique())
    print("age categories:", ages)
    total = df[df[age_col] == "TOTAL"].groupby(["geo", "year"])["value"].sum().rename("cars_total")
    old_codes = [a for a in ages if a.startswith("Y10") or a.startswith("Y_GE10") or a.startswith("Y_GT10")
                 or a.startswith("Y_GE20") or a.startswith("Y_GT20") or a.startswith("Y20")]
    print("age>=10 codes used:", old_codes)
    old = df[df[age_col].isin(old_codes)].groupby(["geo", "year"])["value"].sum().rename("cars_age_ge10")
    out = pd.concat([total, old], axis=1).reset_index()
    out["share_age_ge10"] = out["cars_age_ge10"] / out["cars_total"]
    out = out.dropna(subset=["cars_total"])
    out["has_age"] = out["share_age_ge10"].notna()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(OUT, index=False)
    latest = out[out["has_age"]].sort_values("year").groupby("geo").tail(1)
    print(f"{OUT}: {len(out)} rows, years {out['year'].min()}..{out['year'].max()}")
    print(latest.sort_values("cars_total", ascending=False).head(12).round(3).to_string(index=False))


if __name__ == "__main__":
    main()
