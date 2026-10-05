"""S3: 2027 scenario plan sheet.

fit_base()   : refit every adopted model (incl. Chronos-2) on full history -> base_forecast_2027.parquet.
               Local step; needs torch when a series adopted M3_chronos.
run()        : scenario arithmetic on the saved base forecast (no model fitting) -> plan_2027.parquet.
               This is what the dashboard calls, so it runs without torch.
Base         : saved base forecast; unit price = last-12m USD/kg adjusted by CPT(6) x lead assumption.
US local production    : Base kg minus delta x incremental local output (ramped) for the US series.
Mix shift    : Base kg with unit price lifted by AGM share/premium assumption.

Output: data/processed/plan_2027.parquet, data/processed/reallocation_2027.parquet
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from core_pipeline import series as S
from core_pipeline.baseline_models import sarima, seasonal_naive, stl_ets

P = Path("data/processed")
MODEL_FN = {"M0_snaive": seasonal_naive, "M1_stl_ets": stl_ets, "M2_sarima": sarima}


def load_params() -> dict:
    return json.load(open("data/scenarios.json"))


def conformal_quantiles(series: str, model: str) -> pd.DataFrame:
    fc = pd.read_parquet(P / "backtest_forecasts.parquet")
    f = fc[(fc["series"] == series) & (fc["model"] == model)].copy()
    f["r"] = (np.log1p(f["y_true"]) - np.log1p(f["y_hat"])).abs()
    q = f.groupby("h")["r"].quantile([0.8, 0.95]).unstack()
    q.columns = ["q80", "q95"]
    return q


def model_fn(model: str):
    if model in MODEL_FN:
        return MODEL_FN[model]
    if model == "M3_chronos":
        from core_pipeline.baseline_models import ChronosForecaster
        c = ChronosForecaster()
        if not c.available():
            raise RuntimeError("M3_chronos adopted but chronos is not installed; run fit_base locally with chronos")
        return c.forecast
    raise KeyError(model)


def fit_base(horizon_end: str | None = None) -> pd.DataFrame:
    """Refit every adopted model on full history and save the 2027 base forecast.
    Runs locally (needs torch when a series adopted M3_chronos). The app never calls this."""
    prm = load_params()
    horizon_end = horizon_end or prm["horizon"]["end"]
    adopted = pd.read_parquet(P / "adopted_models.parquet").set_index("series")["model"]
    series = S.load()
    frames = []
    for name, y in series.items():
        frames.append(base_forecast(name, y.dropna(), adopted[name], horizon_end).assign(model=adopted[name]))
    base = pd.concat(frames, ignore_index=True)
    base.to_parquet(P / "base_forecast_2027.parquet", index=False)
    return base


def base_forecast(name: str, y: pd.Series, model: str, horizon_end: str) -> pd.DataFrame:
    last = y.index[-1]
    months = pd.date_range(last + pd.offsets.MonthBegin(1), horizon_end, freq="MS")
    h = len(months)
    yhat = np.clip(model_fn(model)(y, h), 0, None)
    q = conformal_quantiles(name, model)
    rows = []
    for i, d in enumerate(months):
        hh = min(i + 1, int(q.index.max()))
        lp = np.log1p(yhat[i])
        rows.append(dict(series=name, month=d, h=i + 1, kg_point=yhat[i],
                         kg_lo80=np.expm1(lp - q.loc[hh, "q80"]), kg_hi80=np.expm1(lp + q.loc[hh, "q80"]),
                         kg_lo95=np.expm1(lp - q.loc[hh, "q95"]), kg_hi95=np.expm1(lp + q.loc[hh, "q95"])))
    return pd.DataFrame(rows)


def ramp_fraction(months: pd.DatetimeIndex, start: str, end: str) -> np.ndarray:
    s, e = pd.Timestamp(start), pd.Timestamp(end)
    n = max((e.year - s.year) * 12 + (e.month - s.month), 1)
    k = ((months.year - s.year) * 12 + (months.month - s.month)).to_numpy()
    return np.clip(k / n, 0, 1)


def run(delta: float | None = None, agm_share: float | None = None, agm_premium: float | None = None,
        lead_change: float | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    prm = load_params()
    delta = prm["local_ramp"]["delta_default"] if delta is None else delta
    agm_share = prm["mix_shift"]["agm_share_default"] if agm_share is None else agm_share
    agm_premium = prm["mix_shift"]["agm_premium_default"] if agm_premium is None else agm_premium
    lead_change = prm["base"]["lead_change"] if lead_change is None else lead_change
    a0 = prm["mix_shift"]["agm_share_2026"]
    kg_per_unit = prm["kg_per_unit"]
    h_start, h_end = prm["horizon"]["start"], prm["horizon"]["end"]

    bf = P / "base_forecast_2027.parquet"
    if not bf.exists():
        fit_base(h_end)
    base_all = pd.read_parquet(bf)
    adopted = base_all.drop_duplicates("series").set_index("series")["model"]
    sm = pd.read_parquet(P / "series_monthly.parquet")
    pt = pd.read_parquet(P / "pass_through.parquet")
    cpt6 = pt[pt["target"] == "usd_per_kg"].set_index("series")["cpt6"]

    out = []
    for name in adopted.index:
        base = base_all[(base_all["series"] == name) & (base_all["month"] >= h_start)].drop(columns=["model"]).copy()
        g = sm[sm["series"] == name].set_index("date")
        p_last = float(g["usd_per_kg"].iloc[-12:].mean())
        p_base = p_last * np.exp(cpt6.get(name, 0.0) * lead_change)
        mix_factor = (1 + agm_share * (agm_premium - 1)) / (1 + a0 * (agm_premium - 1))

        b = base.assign(scenario="Base", usd_per_kg=p_base)
        out.append(b)

        if name == "US":
            frac = ramp_fraction(pd.DatetimeIndex(base["month"]), prm["local_ramp"]["ramp_start"], prm["local_ramp"]["ramp_end"])
            cut = delta * prm["local_ramp"]["incremental_units_per_year"] * kg_per_unit / 12 * frac
            t = base.copy()
            for c in ["kg_point", "kg_lo80", "kg_hi80", "kg_lo95", "kg_hi95"]:
                t[c] = np.clip(t[c] - cut, 0, None)
            t["displaced_kg"] = cut
            out.append(t.assign(scenario="Local ramp", usd_per_kg=p_base))
        else:
            out.append(base.assign(scenario="Local ramp", usd_per_kg=p_base, displaced_kg=0.0))

        out.append(base.assign(scenario="Mix shift", usd_per_kg=p_base * mix_factor))

    plan = pd.concat(out, ignore_index=True)
    plan["displaced_kg"] = plan.get("displaced_kg", 0.0).fillna(0.0)
    plan["usd"] = plan["kg_point"] * plan["usd_per_kg"]
    plan["model"] = plan["series"].map(adopted)
    plan.attrs.update(delta=delta, agm_share=agm_share, agm_premium=agm_premium, lead_change=lead_change)
    plan.to_parquet(P / "plan_2027.parquet", index=False)

    realloc = reallocation(plan, sm, delta, prm)
    realloc.to_parquet(P / "reallocation_2027.parquet", index=False)
    return plan, realloc


def reallocation(plan: pd.DataFrame, sm: pd.DataFrame, delta: float, prm: dict) -> pd.DataFrame:
    us = plan[(plan["series"] == "US") & (plan["scenario"] == "Local ramp")]
    freed = float(us["displaced_kg"].sum())
    rows = []
    for name in ["JP", "AU", "GB", "CA"]:
        g = sm[sm["series"] == name].set_index("date")["kg"]
        last12 = float(g.iloc[-12:].sum())
        prev12 = float(g.iloc[-24:-12].sum())
        b2027 = float(plan[(plan["series"] == name) & (plan["scenario"] == "Base")]["kg_point"].sum())
        rows.append(dict(series=name, kg_last12m=last12, yoy_growth=last12 / prev12 - 1,
                         kg_2027_base=b2027, freed_share_of_market=freed / b2027 if b2027 else np.nan))
    df = pd.DataFrame(rows)
    df.attrs["freed_kg_2027"] = freed
    df["freed_kg_2027"] = freed
    df["delta"] = delta
    return df
