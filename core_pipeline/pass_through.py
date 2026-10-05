"""S1: lead-price pass-through into export unit price, by destination.

Per series:  dlog p_t = a + sum_{k=0..K} b_k dlog L_{t-k} + g dlog fx_t + month dummies + e_t
HAC (Newey-West) standard errors. CPT(h) = sum_{k<=h} b_k.
A second regression on dlog kg tests H5 (lead price should not move volume).
"""

from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy.stats import norm

P = Path("data/processed")
K = 6


def load_inputs() -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    s = pd.read_parquet(P / "series_monthly.parquet")
    lead = pd.read_parquet(P / "lead_price_monthly.parquet").set_index("date")["lead_usd_mt"]
    fx = pd.read_parquet(P / "fx_monthly.parquet").set_index("date")["krw_per_usd"]
    return s, lead, fx


def design(y: pd.Series, lead: pd.Series, fx: pd.Series) -> tuple[pd.Series, pd.DataFrame]:
    df = pd.DataFrame({"y": np.log(y)})
    dl = np.log(lead).diff()
    for k in range(K + 1):
        df[f"dlead_l{k}"] = dl.shift(k)
    df["dfx"] = np.log(fx).diff()
    df["dy"] = df["y"].diff()
    df["month"] = df.index.month
    df = df.dropna(subset=["dy"] + [f"dlead_l{k}" for k in range(K + 1)] + ["dfx"])
    X = df[[f"dlead_l{k}" for k in range(K + 1)] + ["dfx"]].copy()
    X = pd.concat([X, pd.get_dummies(df["month"], prefix="m", drop_first=True, dtype=float)], axis=1)
    X = sm.add_constant(X)
    return df["dy"], X


def fit(y: pd.Series, lead: pd.Series, fx: pd.Series, maxlags: int = 6) -> dict:
    dy, X = design(y, lead, fx)
    res = sm.OLS(dy, X).fit(cov_type="HAC", cov_kwds={"maxlags": maxlags})
    names = [f"dlead_l{k}" for k in range(K + 1)]
    b = res.params[names].to_numpy()
    cov = res.cov_params().loc[names, names].to_numpy()
    out = {"n": int(res.nobs), "r2": float(res.rsquared)}
    for h in (0, 3, 6):
        w = np.array([1.0 if k <= h else 0.0 for k in range(K + 1)])
        cpt = float(w @ b)
        se = float(np.sqrt(w @ cov @ w))
        out[f"cpt{h}"] = cpt
        out[f"cpt{h}_se"] = se
        out[f"cpt{h}_p"] = float(2 * (1 - norm.cdf(abs(cpt / se)))) if se > 0 else np.nan
    out["peak_lag"] = int(np.argmax(b))
    out["fx_beta"] = float(res.params["dfx"])
    return out


def run() -> pd.DataFrame:
    s, lead, fx = load_inputs()
    rows = []
    for name, g in s.groupby("series"):
        g = g.set_index("date")
        for target in ["usd_per_kg", "kg"]:
            y = g[target].where(g[target] > 0).dropna()
            r = fit(y, lead.reindex(y.index).ffill(), fx.reindex(y.index).ffill())
            r.update(series=name, target=target)
            rows.append(r)
    out = pd.DataFrame(rows)
    out.to_parquet(P / "pass_through.parquet", index=False)
    return out


def verdicts(pt: pd.DataFrame, targets=("US", "JP", "AU", "GB", "CA")) -> dict:
    price = pt[(pt["target"] == "usd_per_kg") & pt["series"].isin(targets)].set_index("series")
    spread = price["cpt3"].max() - price["cpt3"].min()
    n_sig = int((price["cpt3_p"] < 0.05).sum())
    h4 = spread > 0.20 and n_sig >= 3
    vol = pt[(pt["target"] == "kg") & pt["series"].isin(targets)].set_index("series")
    h5 = int((vol["cpt6_p"] >= 0.05).sum()) >= 4
    return {"H4_spread_pp": round(spread * 100, 1), "H4_n_sig": n_sig, "H4": h4,
            "H5_n_insig_volume": int((vol["cpt6_p"] >= 0.05).sum()), "H5": h5}
