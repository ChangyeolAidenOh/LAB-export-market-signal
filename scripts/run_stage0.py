"""Stage 0 summary: coverage, top destinations, cross-source sanity checks.

Usage:
    python -m scripts.run_stage0
"""

from pathlib import Path

import pandas as pd

P = Path("data/processed")


def main() -> None:
    ex = pd.read_parquet(P / "export_monthly.parquet")
    us = pd.read_parquet(P / "us_import_monthly.parquet")
    lead = pd.read_parquet(P / "lead_price_monthly.parquet")
    fx = pd.read_parquet(P / "fx_monthly.parquet")

    ex["year"] = ex["date"].dt.year
    print(f"export_monthly: {ex['date'].min():%Y-%m}..{ex['date'].max():%Y-%m}, "
          f"{ex['country_code'].nunique()} countries, hs={sorted(ex['hs_cd'].unique())}")

    cov = ex.groupby("country_code")["date"].nunique().sort_values(ascending=False)
    print(f"months per country: full={int((cov == cov.max()).sum())}, "
          f"min={int(cov.min())}, median={int(cov.median())}")

    ann = ex.pivot_table(index=["country_code", "country"], columns="year",
                         values="exp_kg", aggfunc="sum", fill_value=0)
    ann_usd = ex.pivot_table(index=["country_code", "country"], columns="year",
                             values="exp_usd", aggfunc="sum", fill_value=0)
    key = ann[[2023, 2024, 2025]].sum(axis=1)
    top = key.sort_values(ascending=False).head(15).index
    tbl = pd.DataFrame({
        "kg_2023_M": (ann.loc[top, 2023] / 1e6).round(1),
        "kg_2024_M": (ann.loc[top, 2024] / 1e6).round(1),
        "kg_2025_M": (ann.loc[top, 2025] / 1e6).round(1),
        "kg_2026ytd_M": (ann.loc[top, 2026] / 1e6).round(1) if 2026 in ann.columns else 0,
        "usd_2025_M": (ann_usd.loc[top, 2025] / 1e6).round(1),
        "usd_per_kg_2025": (ann_usd.loc[top, 2025] / ann.loc[top, 2025]).round(2),
        "share_2325": (key.loc[top] / key.sum()).round(3),
    })
    print("\nTop 15 destinations (2023-2025 cumulative kg):")
    print(tbl.to_string())
    print(f"\nWorld kg 2025: {ann[2025].sum() / 1e6:.1f}M, USD 2025: {ann_usd[2025].sum() / 1e6:.1f}M")

    usk = us[(us["origin"] == "South Korea") & (us["hts10"] == "8507100060")]
    usk = usk.set_index("date")[["qty_units", "value_usd"]].sort_index()
    kr_us = ex[ex["country_code"] == "US"].set_index("date")[["exp_kg", "exp_usd"]].sort_index()
    j = kr_us.join(usk, how="inner")
    for lag in [0, 1, 2]:
        c = j["exp_kg"].corr(j["qty_units"].shift(-lag))
        print(f"KCS kg vs USITC units, US imports lagged {lag}m: corr={c:.3f}")
    ratio = (j["exp_usd"] / j["value_usd"])
    print(f"KCS usd / USITC customs value (US, 0060): median={ratio.median():.2f}, "
          f"2025={ratio['2025'].median():.2f}")
    kg_per_unit = j["exp_kg"] / j["qty_units"]
    print(f"implied kg per unit (KCS kg / USITC units): median={kg_per_unit.median():.1f}")

    print(f"\nlead: {lead['date'].min():%Y-%m}..{lead['date'].max():%Y-%m}, "
          f"min={lead['lead_usd_mt'].min():.0f}, max={lead['lead_usd_mt'].max():.0f}")
    print(f"fx: {fx['date'].min():%Y-%m}..{fx['date'].max():%Y-%m}, "
          f"min={fx['krw_per_usd'].min():.0f}, max={fx['krw_per_usd'].max():.0f}")

    zero = ex.assign(z=ex["exp_kg"] == 0).groupby("country_code")["z"].mean().loc[top.get_level_values(0)]
    print("\nzero-month share, top destinations:")
    print(zero.round(2).to_string())


if __name__ == "__main__":
    main()
