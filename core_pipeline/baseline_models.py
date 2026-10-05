"""Baseline forecasters for monthly export series.

M0 seasonal naive, M1 STL+ETS, M2 SARIMA, M3 Chronos zero-shot (optional).
Every model exposes forecast(y, h) -> np.ndarray of length h (point forecast).
"""

import warnings

import numpy as np
import pandas as pd
from statsmodels.tsa.forecasting.stl import STLForecast
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from statsmodels.tsa.statespace.sarimax import SARIMAX

warnings.filterwarnings("ignore")

PERIOD = 12


def seasonal_naive(y: pd.Series, h: int) -> np.ndarray:
    vals = y.to_numpy()
    out = []
    for i in range(1, h + 1):
        out.append(vals[-PERIOD + ((i - 1) % PERIOD)])
    return np.array(out, dtype=float)


def stl_ets(y: pd.Series, h: int) -> np.ndarray:
    z = np.log1p(y.clip(lower=0))
    stlf = STLForecast(z, ExponentialSmoothing,
                       model_kwargs=dict(trend="add", damped_trend=True, initialization_method="estimated"),
                       period=PERIOD, robust=True)
    res = stlf.fit()
    fc = res.forecast(h)
    return np.expm1(np.asarray(fc, dtype=float))


def sarima(y: pd.Series, h: int) -> np.ndarray:
    z = np.log1p(y.clip(lower=0))
    mod = SARIMAX(z, order=(1, 1, 1), seasonal_order=(0, 1, 1, PERIOD),
                  enforce_stationarity=False, enforce_invertibility=False)
    res = mod.fit(disp=False, maxiter=200)
    fc = res.forecast(h)
    return np.expm1(np.asarray(fc, dtype=float))


class ChronosForecaster:
    """Zero-shot Chronos. Tries amazon/chronos-2, then chronos-bolt-small."""

    def __init__(self, context: int = 60):
        self.context = context
        self.pipe = None
        self.name = None
        try:
            import torch
            from chronos import BaseChronosPipeline
            for model_id in ["amazon/chronos-2", "amazon/chronos-bolt-small"]:
                try:
                    self.pipe = BaseChronosPipeline.from_pretrained(model_id, device_map="cpu", torch_dtype=torch.float32)
                    self.name = model_id
                    break
                except Exception as e:
                    print(f"chronos load failed for {model_id}: {e}")
        except ImportError as e:
            print(f"chronos unavailable: {e}")

    def available(self) -> bool:
        return self.pipe is not None

    def forecast(self, y: pd.Series, h: int) -> np.ndarray:
        import torch
        ctx = torch.tensor(y.to_numpy()[-self.context:], dtype=torch.float32)
        if "chronos-2" in (self.name or ""):
            ctx = ctx.reshape(1, 1, -1)
        try:
            q, _ = self.pipe.predict_quantiles(ctx, prediction_length=h, quantile_levels=[0.1, 0.5, 0.9])
        except TypeError:
            q, _ = self.pipe.predict_quantiles(context=ctx, prediction_length=h, quantile_levels=[0.1, 0.5, 0.9])
        q = q[0] if isinstance(q, (list, tuple)) else q
        arr = np.asarray(q.detach().cpu().numpy() if hasattr(q, "detach") else q, dtype=float)
        while arr.ndim > 2:
            arr = arr[0]
        return arr[:, 1] if arr.ndim == 2 else arr


def build_models(with_chronos: bool = False) -> dict:
    models = {"M0_snaive": seasonal_naive, "M1_stl_ets": stl_ets, "M2_sarima": sarima}
    if with_chronos:
        c = ChronosForecaster()
        if c.available():
            models["M3_chronos"] = c.forecast
            print(f"chronos: {c.name}")
    return models
