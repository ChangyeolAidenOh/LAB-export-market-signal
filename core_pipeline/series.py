"""Build the six target series (top-5 destinations + World) from export_monthly.parquet.

Output: data/processed/series_monthly.parquet
    columns: series, date, kg, usd, usd_per_kg
"""

from pathlib import Path

import pandas as pd

P = Path("data/processed")
TARGETS = ["US", "JP", "AU", "GB", "CA"]


def build() -> pd.DataFrame:
    ex = pd.read_parquet(P / "export_monthly.parquet")
    idx = pd.date_range(ex["date"].min(), ex["date"].max(), freq="MS")
    frames = []
    for c in TARGETS:
        g = ex[ex["country_code"] == c].groupby("date")[["exp_kg", "exp_usd"]].sum().reindex(idx, fill_value=0)
        g["series"] = c
        frames.append(g)
    w = ex.groupby("date")[["exp_kg", "exp_usd"]].sum().reindex(idx, fill_value=0)
    w["series"] = "WORLD"
    frames.append(w)
    out = pd.concat(frames).rename_axis("date").reset_index()
    out = out.rename(columns={"exp_kg": "kg", "exp_usd": "usd"})
    out["usd_per_kg"] = out["usd"] / out["kg"].where(out["kg"] > 0)
    out = out[["series", "date", "kg", "usd", "usd_per_kg"]].sort_values(["series", "date"]).reset_index(drop=True)
    out.to_parquet(P / "series_monthly.parquet", index=False)
    return out


def load() -> dict[str, pd.Series]:
    f = P / "series_monthly.parquet"
    df = pd.read_parquet(f) if f.exists() else build()
    return {s: g.set_index("date")["kg"].asfreq("MS") for s, g in df.groupby("series")}


if __name__ == "__main__":
    df = build()
    print(df.groupby("series")["date"].agg(["min", "max", "count"]))
