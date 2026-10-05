"""Rolling-origin backtest with rolling conformal bands.

Origins: the last `n_test` month-starts such that h_max steps are observed,
preceded by `n_cal` calibration origins used only to seed conformal residuals.
For test fold k, the band at horizon h uses the empirical quantile of |error|
from all earlier folds at the same horizon.

Outputs
    forecasts: series, model, origin, h, target_date, y_true, y_hat, lo80, hi80, lo95, hi95
    scores:    series, model, h, mase, smape, cov80, cov95, width80
"""

import numpy as np
import pandas as pd

from core_pipeline.baseline_models import PERIOD

HORIZONS = (1, 3, 6)


def mase_scale(y_train: pd.Series) -> float:
    v = y_train.to_numpy()
    return float(np.mean(np.abs(v[PERIOD:] - v[:-PERIOD])))


def run(series: dict[str, pd.Series], models: dict, n_test: int = 12, n_cal: int = 12,
        h_max: int = 6, log_resid: bool = True) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    for name, y in series.items():
        y = y.dropna()
        last_origin = y.index[-1 - h_max]
        origins = pd.date_range(end=last_origin, periods=n_test + n_cal, freq="MS")
        for mname, fn in models.items():
            resid = {h: [] for h in range(1, h_max + 1)}
            for k, origin in enumerate(origins):
                train = y[:origin]
                test = y[origin + pd.offsets.MonthBegin(1):][:h_max]
                scale = mase_scale(train)
                try:
                    yhat = fn(train, h_max)
                except Exception as e:
                    print(f"{name} {mname} {origin:%Y-%m}: {e}")
                    continue
                for i, (td, yt) in enumerate(test.items()):
                    h = i + 1
                    pred = max(float(yhat[i]), 0.0)
                    err = np.log1p(yt) - np.log1p(pred) if log_resid else yt - pred
                    is_test = k >= n_cal
                    lo80 = hi80 = lo95 = hi95 = np.nan
                    if is_test and len(resid[h]) >= 6:
                        r = np.abs(np.array(resid[h]))
                        q80, q95 = np.quantile(r, 0.8), np.quantile(r, 0.95)
                        if log_resid:
                            lp = np.log1p(pred)
                            lo80, hi80 = np.expm1(lp - q80), np.expm1(lp + q80)
                            lo95, hi95 = np.expm1(lp - q95), np.expm1(lp + q95)
                        else:
                            lo80, hi80, lo95, hi95 = pred - q80, pred + q80, pred - q95, pred + q95
                    resid[h].append(err)
                    rows.append(dict(series=name, model=mname, origin=origin, h=h, target_date=td,
                                     y_true=float(yt), y_hat=pred, lo80=lo80, hi80=hi80,
                                     lo95=lo95, hi95=hi95, mase_scale=scale, is_test=is_test))
    fc = pd.DataFrame(rows)
    t = fc[fc["is_test"]].copy()
    t["ae"] = (t["y_true"] - t["y_hat"]).abs()
    t["smape"] = 2 * t["ae"] / (t["y_true"].abs() + t["y_hat"].abs())
    t["in80"] = (t["y_true"] >= t["lo80"]) & (t["y_true"] <= t["hi80"])
    t["in95"] = (t["y_true"] >= t["lo95"]) & (t["y_true"] <= t["hi95"])
    t["w80"] = (t["hi80"] - t["lo80"]) / t["y_true"]
    sc = (t.groupby(["series", "model", "h"])
            .apply(lambda g: pd.Series({
                "mase": (g["ae"] / g["mase_scale"]).mean(),
                "smape": g["smape"].mean(),
                "cov80": g["in80"].mean(),
                "cov95": g["in95"].mean(),
                "width80": g["w80"].mean(),
                "n": len(g)}), include_groups=False)
            .reset_index())
    return fc, sc


def adopt(scores: pd.DataFrame, horizons=(1, 2, 3)) -> pd.DataFrame:
    s = scores[scores["h"].isin(horizons)].groupby(["series", "model"]).agg(
        mase=("mase", "mean"), cov80=("cov80", "mean")).reset_index()
    s["eligible"] = s["cov80"].between(0.70, 0.90)
    picks = []
    for name, g in s.groupby("series"):
        g2 = g[g["eligible"]] if g["eligible"].any() else g
        picks.append(g2.sort_values("mase").iloc[0])
    return pd.DataFrame(picks).reset_index(drop=True)
