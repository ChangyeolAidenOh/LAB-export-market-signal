"""S4: EU white space — where replacement demand is large and Korean share is low.

Score per member state (0-100, rank-normalised z-score blend):
    demand   : log(passenger cars aged >=10y)                 (Eurostat road_eqs_carage)
    market   : log(total imports of CN 8507 10, EUR, 2024-25) (Comext)
    headroom : 1 - Korean import share (value, 2024-25)
    growth   : import growth 2025 vs 2023
Weights are a parameter; three weight sets are reported for rank sensitivity.
"""

from pathlib import Path

import numpy as np
import pandas as pd

P = Path("data/processed")
WEIGHTS = {
    "balanced": {"demand": 0.35, "market": 0.35, "headroom": 0.20, "growth": 0.10},
    "demand_led": {"demand": 0.50, "market": 0.25, "headroom": 0.15, "growth": 0.10},
    "headroom_led": {"demand": 0.25, "market": 0.25, "headroom": 0.40, "growth": 0.10},
}
BIG = ["DE", "FR", "IT", "ES", "PL", "NL", "BE", "SE", "AT", "CZ", "PT", "RO", "HU", "GR", "DK"]


def features() -> pd.DataFrame:
    eu = pd.read_parquet(P / "eu_import_monthly.parquet")
    eu["year"] = eu["date"].dt.year
    w = eu[eu["partner"] == "WORLD"].groupby(["reporter", "year"])["value_eur"].sum().unstack("year")
    kr = eu[eu["partner"] == "KR"].groupby(["reporter", "year"])["value_eur"].sum().unstack("year").reindex(w.index).fillna(0)
    cn = eu[eu["partner"] == "CN"].groupby(["reporter", "year"])["value_eur"].sum().unstack("year").reindex(w.index).fillna(0)
    agm = eu[(eu["partner"] == "WORLD") & (eu["year"] == 2025)].pivot_table(index="reporter", columns="cn8", values="value_eur", aggfunc="sum")
    f = pd.DataFrame(index=w.index)
    f["imports_eur_m"] = (w[2024] + w[2025]) / 2 / 1e6
    f["kr_share"] = (kr[2024] + kr[2025]) / (w[2024] + w[2025])
    f["cn_share"] = (cn[2024] + cn[2025]) / (w[2024] + w[2025])
    f["growth_25_23"] = w[2025] / w[2023] - 1
    f["agm_share_2025"] = agm["85071080"] / agm.sum(axis=1)

    parc = pd.read_parquet(P / "eu_car_parc.parquet")
    parc = parc[parc["has_age"]].sort_values("year").groupby("geo").tail(1).set_index("geo")
    parc.index = parc.index.str.replace("EL", "GR")
    f["cars_total_m"] = parc["cars_total"].reindex(f.index) / 1e6
    f["cars_ge10_m"] = parc["cars_age_ge10"].reindex(f.index) / 1e6
    f["share_age_ge10"] = parc["share_age_ge10"].reindex(f.index)
    f["parc_year"] = parc["year"].reindex(f.index)
    return f


def _z(s: pd.Series) -> pd.Series:
    return (s - s.mean()) / s.std(ddof=0)


def score(f: pd.DataFrame, weights: dict) -> pd.Series:
    comp = pd.DataFrame({
        "demand": _z(np.log(f["cars_ge10_m"].clip(lower=0.01))),
        "market": _z(np.log(f["imports_eur_m"].clip(lower=0.1))),
        "headroom": _z(1 - f["kr_share"].fillna(0)),
        "growth": _z(f["growth_25_23"].clip(-0.5, 1.0).fillna(0)),
    })
    raw = sum(comp[k] * v for k, v in weights.items())
    return ((raw - raw.min()) / (raw.max() - raw.min()) * 100).round(1)


def run() -> pd.DataFrame:
    f = features()
    f = f.dropna(subset=["cars_ge10_m", "imports_eur_m"])
    for name, w in WEIGHTS.items():
        f[f"score_{name}"] = score(f, w)
        f[f"rank_{name}"] = f[f"score_{name}"].rank(ascending=False).astype(int)
    f["rank_spread"] = f[[c for c in f.columns if c.startswith("rank_")]].max(axis=1) - f[[c for c in f.columns if c.startswith("rank_")]].min(axis=1)
    f = f.sort_values("score_balanced", ascending=False)
    f.to_parquet(P / "white_space.parquet")
    return f
