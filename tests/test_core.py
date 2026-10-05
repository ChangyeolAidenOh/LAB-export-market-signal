import json

import numpy as np
import pandas as pd
import pytest

from core_pipeline import backtest, changepoint
from core_pipeline.baseline_models import seasonal_naive, stl_ets
from core_pipeline.scenarios import ramp_fraction


def synthetic_series(n=108, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2018-01-01", periods=n, freq="MS")
    season = 1 + 0.2 * np.sin(2 * np.pi * np.arange(n) / 12)
    trend = np.linspace(10e6, 20e6, n)
    y = trend * season * rng.lognormal(0, 0.08, n)
    return pd.Series(y, index=idx)


def test_seasonal_naive_repeats_last_year():
    y = synthetic_series()
    fc = seasonal_naive(y, 3)
    assert np.allclose(fc, y.to_numpy()[-12:-9])


def test_stl_ets_positive_and_right_length():
    y = synthetic_series()
    fc = stl_ets(y, 6)
    assert len(fc) == 6 and (fc > 0).all()


def test_mase_scale_is_mean_abs_seasonal_diff():
    y = synthetic_series()
    v = y.to_numpy()
    assert backtest.mase_scale(y) == pytest.approx(np.mean(np.abs(v[12:] - v[:-12])))


def test_backtest_conformal_coverage_reasonable():
    series = {"A": synthetic_series(seed=1)}
    fc, sc = backtest.run(series, {"M0_snaive": seasonal_naive}, n_test=12, n_cal=12)
    assert set(sc["h"]) == {1, 2, 3, 4, 5, 6}
    cov = sc[sc["h"] <= 3]["cov80"].mean()
    assert 0.5 <= cov <= 1.0
    t = fc[fc["is_test"]]
    assert (t["lo80"] <= t["y_hat"]).all() and (t["hi80"] >= t["y_hat"]).all()


def test_pelt_detects_injected_level_shift():
    y = synthetic_series(seed=2)
    y.iloc[60:] *= 1.8
    sa = changepoint.seasonal_adjust(y)
    dates = changepoint.pelt(sa, model="l2")
    assert changepoint.in_window(dates, "2023-01-01", months=2)


def test_ramp_fraction_linear_and_clipped():
    months = pd.date_range("2026-07-01", "2028-03-01", freq="MS")
    f = ramp_fraction(months, "2026-10-01", "2027-12-01")
    assert f[0] == 0 and f[-1] == 1
    assert np.all(np.diff(f) >= 0)
    assert f[list(months).index(pd.Timestamp("2027-05-01"))] == pytest.approx(7 / 14)


def test_mix_factor_increases_with_agm_share():
    a0, m = 0.20, 1.5
    f = lambda a1: (1 + a1 * (m - 1)) / (1 + a0 * (m - 1))
    assert f(0.20) == pytest.approx(1.0)
    assert f(0.30) > 1.0 and f(0.30) == pytest.approx(1.15 / 1.10)


def test_events_json_has_fixed_schema():
    ev = json.load(open("data/events.json"))
    assert ev["hs"] == "850710"
    ids = [e["id"] for e in ev["events"]]
    assert ids == sorted(ids) and "E1" in ids
    for e in ev["events"]:
        pd.Timestamp(e["date"])
        assert e["type"] in {"tariff", "supply", "market"}
