"""Exploratory analyses (NOT pre-registered). Written to docs/exploratory.md.

E1. Trend-break PELT (piecewise-linear cost) on the US series: does the slope change in 2025H2?
E2. Front-loading before the April 2025 tariff: excess shipments vs a baseline fit through Feb 2025,
    and the payback in the following months.
E3. Model adoption if the 80%-coverage window were relaxed to [0.70, 0.95].

Usage:
    python -m scripts.run_exploratory
"""

from pathlib import Path

import numpy as np
import pandas as pd
import ruptures as rpt

from core_pipeline import series as S
from core_pipeline.backtest import adopt
from core_pipeline.baseline_models import stl_ets
from core_pipeline.changepoint import seasonal_adjust

P = Path("data/processed")
OUT = Path("docs/exploratory.md")


def trend_breaks(sa: pd.Series, min_size: int = 9) -> list[pd.Timestamp]:
    n = len(sa)
    t = np.arange(n, dtype=float) / n
    signal = np.column_stack([sa.to_numpy(), t, np.ones(n)])
    resid_var = float(np.var(np.diff(sa.to_numpy())))
    pen = 3 * np.log(n) * resid_var
    bks = rpt.Pelt(model="linear", min_size=min_size, jump=1).fit(signal).predict(pen=pen)
    return [sa.index[b] for b in bks if b < n]


def slopes(sa: pd.Series, breaks: list[pd.Timestamp]) -> list[tuple[str, str, float]]:
    bounds = [sa.index[0]] + list(breaks) + [sa.index[-1] + pd.offsets.MonthBegin(1)]
    out = []
    for a, b in zip(bounds[:-1], bounds[1:]):
        seg = sa[(sa.index >= a) & (sa.index < b)]
        if len(seg) >= 3:
            x = np.arange(len(seg))
            k = np.polyfit(x, seg.to_numpy(), 1)[0]
            out.append((f"{a:%Y-%m}", f"{(b - pd.offsets.MonthBegin(1)):%Y-%m}", float(np.expm1(k * 12))))
    return out


def front_loading(y: pd.Series, cutoff: str = "2025-02-01", window: int = 3, payback: int = 4) -> dict:
    train = y[:cutoff]
    fc = stl_ets(train, window + payback)
    idx = y.index[y.index > pd.Timestamp(cutoff)][: window + payback]
    actual = y.reindex(idx)
    fc = pd.Series(fc[: len(idx)], index=idx)
    excess = (actual - fc).iloc[:window].sum()
    pay = (actual - fc).iloc[window:window + payback].sum()
    avg = train.iloc[-12:].mean()
    return {"excess_kg": float(excess), "excess_months": float(excess / avg), "payback_kg": float(pay),
            "payback_months": float(pay / avg), "window": [f"{idx[0]:%Y-%m}", f"{idx[window - 1]:%Y-%m}"],
            "payback_window": [f"{idx[window]:%Y-%m}", f"{idx[min(window + payback, len(idx)) - 1]:%Y-%m}"],
            "detail": pd.DataFrame({"actual_M": actual / 1e6, "baseline_M": fc / 1e6, "gap_M": (actual - fc) / 1e6})
                        .round(1).set_axis(idx.strftime("%Y-%m"))}


def relaxed_adoption() -> pd.DataFrame:
    sc = pd.read_parquet(P / "backtest_scores.parquet")
    strict = adopt(sc).set_index("series")["model"]
    s = sc[sc["h"].isin([1, 2, 3])].groupby(["series", "model"]).agg(mase=("mase", "mean"), cov80=("cov80", "mean")).reset_index()
    s["eligible"] = s["cov80"].between(0.70, 0.95)
    picks = {}
    for name, g in s.groupby("series"):
        g2 = g[g["eligible"]] if g["eligible"].any() else g
        picks[name] = g2.sort_values("mase").iloc[0]["model"]
    return pd.DataFrame({"strict_[0.70,0.90]": strict, "relaxed_[0.70,0.95]": pd.Series(picks)})


def main() -> None:
    series = S.load()
    lines = ["# Exploratory analyses (post-hoc, not pre-registered)", "",
             "_These were run after the pre-registered results were fixed; "
             "they inform interpretation only and are not counted as hypothesis tests._", ""]

    lines += ["## E1. Trend breaks (piecewise-linear PELT on STL-adjusted log kg)", ""]
    for name in ["US", "WORLD", "GB"]:
        sa = seasonal_adjust(series[name].dropna())
        bks = trend_breaks(sa)
        segs = slopes(sa, bks)
        lines.append(f"**{name}** breaks: {', '.join(b.strftime('%Y-%m') for b in bks) if bks else 'none'}")
        lines.append("")
        lines.append("| segment | annualised slope |")
        lines.append("|---|---|")
        for a, b, k in segs:
            lines.append(f"| {a} → {b} | {k:+.0%} |")
        lines.append("")
    lines.append("Reading: the level-shift detector (pre-registered H1) found no break at the tariff; the slope detector shows "
                 "whether the post-April-2025 decline is a change of trend rather than a one-off drop.")
    lines.append("")

    fl = front_loading(series["US"].dropna())
    lines += ["## E2. Front-loading before the April 2025 tariff (US)", "",
              f"Baseline: STL+ETS fit through 2025-02, forecast {fl['window'][0]}..{fl['payback_window'][1]}.", "",
              fl["detail"].to_markdown(), "",
              f"- Excess shipments {fl['window'][0]}..{fl['window'][1]}: **{fl['excess_kg'] / 1e6:+.1f}M kg ≈ {fl['excess_months']:+.2f} months** of the prior-12m average.",
              f"- Payback {fl['payback_window'][0]}..{fl['payback_window'][1]}: {fl['payback_kg'] / 1e6:+.1f}M kg ≈ {fl['payback_months']:+.2f} months.",
              "- If payback roughly offsets the excess, the tariff moved timing more than demand within the first half-year.", ""]

    ra = relaxed_adoption()
    lines += ["## E3. Model adoption under a relaxed coverage window", "", ra.to_markdown(), "",
              "Reading: Chronos-2 wins on point accuracy (H6) but its conformal bands sit outside the strict window on several "
              "series — over-covered (CA, JP) or under-covered (US, WORLD). Relaxing only the upper bound keeps the "
              "pre-registered rule's intent (no under-coverage) and changes which series adopt the foundation model.", ""]

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
