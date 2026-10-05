"""Stage 1: baselines, rolling backtest, conformal bands, changepoints.

Usage:
    python -m scripts.run_stage1
    python -m scripts.run_stage1 --with-chronos
"""

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from core_pipeline import series as S
from core_pipeline.backtest import adopt, run
from core_pipeline.baseline_models import build_models
from core_pipeline.changepoint import detect_all, in_window, seasonal_adjust

P = Path("data/processed")
FIG = Path("docs/figs")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--with-chronos", action="store_true")
    args = ap.parse_args()
    FIG.mkdir(parents=True, exist_ok=True)

    S.build()
    series = S.load()
    models = build_models(args.with_chronos)
    print("models:", list(models))

    fc, sc = run(series, models)
    fc.to_parquet(P / "backtest_forecasts.parquet", index=False)
    sc.to_parquet(P / "backtest_scores.parquet", index=False)

    print("\nMASE by series x model (h=1..3 mean) and 80% coverage:")
    tbl = sc[sc["h"].isin([1, 2, 3])].groupby(["series", "model"]).agg(
        mase=("mase", "mean"), cov80=("cov80", "mean")).round(3).unstack("model")
    print(tbl.to_string())
    print("\nMASE at h=6:")
    print(sc[sc["h"] == 6].pivot(index="series", columns="model", values="mase").round(3).to_string())

    picks = adopt(sc)
    picks.to_parquet(P / "adopted_models.parquet", index=False)
    print("\nAdopted model per series:")
    print(picks.round(3).to_string(index=False))

    if "M3_chronos" in models:
        w = sc[sc["h"].isin([1, 2, 3])].groupby(["series", "model"])["mase"].mean().unstack()
        wins = int((w["M3_chronos"] < w["M1_stl_ets"]).sum())
        print(f"\nH6: Chronos beats STL+ETS on {wins}/6 series -> {'SUPPORTED' if wins >= 4 else 'REJECTED'}")
    else:
        print("\nH6: not tested (chronos not loaded)")

    cps = detect_all(series)
    cps.to_parquet(P / "changepoints.parquet", index=False)
    print("\nChangepoints (PELT on STL-adjusted log kg):")
    for name, g in cps.groupby("series"):
        print(f"  {name}: " + " | ".join(f"{m}: {', '.join(d.strftime('%Y-%m') for d in gg['date'])}"
                                       for m, gg in g.groupby("model")))
    us = cps[cps["series"] == "US"]
    hit = {m: in_window(g["date"], "2025-04-01", 2) for m, g in us.groupby("model")}
    print(f"\nH1 (US changepoint within 2025-04 +/- 2m): {hit} -> "
          f"{'SUPPORTED' if any(hit.values()) else 'REJECTED'}")

    events = json.load(open("data/events.json"))["events"]
    for name, y in series.items():
        fig, ax = plt.subplots(figsize=(10, 4))
        ax.plot(y.index, y / 1e6, color="#333", lw=1.2, label="kg (M)")
        ax.plot(y.index, (y.rolling(3).mean()) / 1e6, color="#1f77b4", lw=1, alpha=0.7, label="3m MA")
        t = fc[(fc["series"] == name) & (fc["model"] == picks.set_index("series").loc[name, "model"]) & fc["is_test"] & (fc["h"] == 1)]
        if not t.empty:
            ax.plot(t["target_date"], t["y_hat"] / 1e6, color="#d62728", lw=1, label="baseline h=1")
            ax.fill_between(t["target_date"], t["lo80"] / 1e6, t["hi80"] / 1e6, color="#d62728", alpha=0.15, label="80% band")
        for _, r in us.iterrows() if name == "US" else cps[cps["series"] == name].iterrows():
            ax.axvline(r["date"], color="gray", ls=":", lw=0.8)
        for e in events:
            if e["type"] == "tariff":
                ax.axvline(pd.Timestamp(e["date"]), color="#ff7f0e", lw=0.8)
        ax.set_title(f"{name}: Korea exports HS 8507.10, kg")
        ax.legend(loc="upper left", fontsize=8)
        fig.tight_layout()
        fig.savefig(FIG / f"baseline_{name}.png", dpi=120)
        plt.close(fig)
    print(f"\nfigures: {FIG}/baseline_*.png")


if __name__ == "__main__":
    main()
