"""PELT changepoints on seasonally adjusted (STL) series."""

import numpy as np
import pandas as pd
import ruptures as rpt
from statsmodels.tsa.seasonal import STL

PERIOD = 12


def seasonal_adjust(y: pd.Series) -> pd.Series:
    z = np.log1p(y.clip(lower=0))
    res = STL(z, period=PERIOD, robust=True).fit()
    return pd.Series(res.trend + res.resid, index=y.index)


def pelt(sa: pd.Series, model: str = "l2", min_size: int = 3) -> list[pd.Timestamp]:
    x = sa.to_numpy().reshape(-1, 1)
    n = len(x)
    if model == "l2":
        sigma2 = float(np.var(np.diff(x, axis=0)))
        pen = 2 * np.log(n) * sigma2
    else:
        x = (x - x.mean()) / x.std()
        pen = 3.0
    algo = rpt.Pelt(model=model, min_size=min_size, jump=1).fit(x)
    bks = algo.predict(pen=pen)
    return [sa.index[b] for b in bks if b < n]


def detect_all(series: dict[str, pd.Series]) -> pd.DataFrame:
    rows = []
    for name, y in series.items():
        sa = seasonal_adjust(y.dropna())
        for m in ["l2", "rbf"]:
            for d in pelt(sa, model=m):
                rows.append(dict(series=name, model=m, date=d))
    return pd.DataFrame(rows)


def in_window(dates, center: str, months: int = 2) -> bool:
    c = pd.Timestamp(center)
    lo, hi = c - pd.DateOffset(months=months), c + pd.DateOffset(months=months)
    return any(lo <= pd.Timestamp(d) <= hi for d in dates)
