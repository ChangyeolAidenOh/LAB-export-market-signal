"""S2: US import origin shares for HTS 8507.10.0060 before and after the April 2025 tariff."""

from pathlib import Path

import pandas as pd

P = Path("data/processed")
HTS = "8507100060"
PRE = ("2024-04-01", "2025-03-01")
POST = ("2025-04-01", "2026-03-01")
YTD = ("2026-01-01", "2026-12-01")
GROUPS = {"South Korea": "Korea", "Mexico": "Mexico", "China": "China", "Vietnam": "Vietnam",
          "Germany": "Germany", "Japan": "Japan", "Malaysia": "Malaysia"}


def load() -> pd.DataFrame:
    us = pd.read_parquet(P / "us_import_monthly.parquet")
    us = us[us["hts10"] == HTS].copy()
    us["origin_grp"] = us["origin"].map(GROUPS).fillna("Other")
    return us


def monthly_shares(us: pd.DataFrame, col: str = "value_usd") -> pd.DataFrame:
    m = us.pivot_table(index="date", columns="origin_grp", values=col, aggfunc="sum", fill_value=0)
    return m.div(m.sum(axis=1), axis=0), m


def window(df: pd.DataFrame, w: tuple[str, str]) -> pd.DataFrame:
    return df.loc[w[0]:w[1]]


def run() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    us = load()
    sh_v, lvl_v = monthly_shares(us, "value_usd")
    sh_q, lvl_q = monthly_shares(us, "qty_units")
    up = us.pivot_table(index="date", columns="origin_grp", values=["value_usd", "qty_units"], aggfunc="sum")
    unit_price = up["value_usd"] / up["qty_units"].where(up["qty_units"] > 0)

    tbl = pd.DataFrame({
        "share_val_pre": window(sh_v, PRE).mean(),
        "share_val_post": window(sh_v, POST).mean(),
        "share_val_2026ytd": window(sh_v, YTD).mean(),
        "share_qty_pre": window(sh_q, PRE).mean(),
        "share_qty_post": window(sh_q, POST).mean(),
        "usd_per_unit_pre": window(unit_price, PRE).mean(),
        "usd_per_unit_post": window(unit_price, POST).mean(),
    })
    tbl["delta_val_pp"] = (tbl["share_val_post"] - tbl["share_val_pre"]) * 100
    tbl["delta_qty_pp"] = (tbl["share_qty_post"] - tbl["share_qty_pre"]) * 100
    tbl = tbl.sort_values("share_val_pre", ascending=False)
    tbl.to_parquet(P / "origin_shift.parquet")

    total_q = lvl_q.sum(axis=1)
    tot_pre, tot_post = window(total_q, PRE).mean(), window(total_q, POST).mean()
    kr_pre = window(sh_q["Korea"], PRE)
    kr_post = window(sh_q["Korea"], POST)
    total_ratio = tot_post / tot_pre
    kr_drop_sd = (kr_pre.mean() - kr_post.mean()) / kr_pre.std()
    h2 = (abs(total_ratio - 1) <= 0.10) and (kr_drop_sd > 1.0)
    gainer = tbl.drop(index="Other", errors="ignore")["delta_val_pp"].idxmax()
    h3 = gainer == "Mexico"
    v = {"H2_total_post_over_pre": round(total_ratio, 3), "H2_korea_share_drop_sd": round(kr_drop_sd, 2),
         "H2": h2, "H3_top_gainer": gainer, "H3": h3}
    monthly = pd.concat({"share_val": sh_v, "share_qty": sh_q, "unit_price": unit_price}, axis=1)
    monthly.to_parquet(P / "origin_shift_monthly.parquet")
    return tbl, monthly, v
