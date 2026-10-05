"""Stage 3: 2027 scenario plan sheet (S3).

Usage:
    python -m scripts.run_stage3
"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from core_pipeline import scenarios

FIG = Path("docs/figs")


def main() -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    plan, realloc = scenarios.run()
    a = plan.attrs
    print(f"params: delta={a['delta']} agm_share={a['agm_share']} agm_premium={a['agm_premium']} lead_change={a['lead_change']}")

    ann = plan.groupby(["series", "scenario"]).agg(kg_M=("kg_point", "sum"), usd_M=("usd", "sum"),
                                                   lo80_M=("kg_lo80", "sum"), hi80_M=("kg_hi80", "sum")).reset_index()
    for c in ["kg_M", "usd_M", "lo80_M", "hi80_M"]:
        ann[c] = (ann[c] / 1e6).round(1)
    print("\n2027 annual plan by series x scenario (kg M, USD M; 80% band is sum of monthly bounds):")
    print(ann.pivot(index="series", columns="scenario", values=["kg_M", "usd_M"]).to_string())

    sm = pd.read_parquet("data/processed/series_monthly.parquet")
    ref = sm[sm["date"].dt.year == 2025].groupby("series")[["kg", "usd"]].sum() / 1e6
    print("\n2025 actual for reference (kg M, USD M):")
    print(ref.round(1).to_string())

    print(f"\nUS local production ramp: displaced Korea->US kg in 2027 = {realloc['freed_kg_2027'].iloc[0] / 1e6:.1f}M "
          f"(delta={realloc['delta'].iloc[0]})")
    print("Reallocation candidates (non-US top markets):")
    r = realloc.copy()
    r["kg_last12m"] = (r["kg_last12m"] / 1e6).round(1)
    r["kg_2027_base"] = (r["kg_2027_base"] / 1e6).round(1)
    r["yoy_growth"] = (r["yoy_growth"] * 100).round(1)
    r["freed_share_of_market"] = (r["freed_share_of_market"] * 100).round(0)
    print(r[["series", "kg_last12m", "yoy_growth", "kg_2027_base", "freed_share_of_market"]].to_string(index=False))

    us = plan[plan["series"] == "US"]
    hist = sm[sm["series"] == "US"].set_index("date")["kg"]
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(hist.index[-36:], hist.iloc[-36:] / 1e6, color="#333", lw=1.2, label="actual")
    for sc, col in [("Base", "#1f77b4"), ("US local production ramp", "#d62728")]:
        g = us[us["scenario"] == sc]
        ax.plot(g["month"], g["kg_point"] / 1e6, color=col, lw=1.5, label=sc)
        if sc == "Base":
            ax.fill_between(g["month"], g["kg_lo80"] / 1e6, g["kg_hi80"] / 1e6, color=col, alpha=0.15)
    ax.set_title(f"US: 2027 plan scenarios (kg M), delta={a['delta']}")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(FIG / "s3_us_2027.png", dpi=120)
    plt.close(fig)
    print(f"\nfigure: {FIG}/s3_us_2027.png")


if __name__ == "__main__":
    main()
