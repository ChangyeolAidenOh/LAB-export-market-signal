"""Pull monthly average KRW/USD from ECOS (Bank of Korea).

Usage:
    python -m core_pipeline.ingest_fx
    python -m core_pipeline.ingest_fx --list

The exact stat/item combination for the monthly series varies, so the script
queries StatisticItemList for candidate tables, picks the USD item, and tries
each item combination at monthly frequency until one returns data.
Output: data/processed/fx_monthly.parquet with columns date, krw_per_usd
"""

import argparse
import itertools
from pathlib import Path

import pandas as pd
import requests

from core_pipeline.config import get_env

OUT = Path("data/processed/fx_monthly.parquet")
BASE = "https://ecos.bok.or.kr/api"
CANDIDATE_STATS = ["731Y003", "731Y001", "731Y004", "731Y005"]
USD_PATTERN = "미국달러|미 달러|USD"


def ecos_get(key: str, service: str, path: str) -> dict:
    url = f"{BASE}/{service}/{key}/json/kr/1/1000/{path}"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.json()


def list_items(key: str, stat: str) -> pd.DataFrame:
    js = ecos_get(key, "StatisticItemList", stat)
    if "StatisticItemList" not in js:
        return pd.DataFrame()
    return pd.DataFrame(js["StatisticItemList"]["row"])


def try_search(key: str, stat: str, items: list[str], start: str, end: str):
    path = f"{stat}/M/{start}/{end}/" + "/".join(items)
    js = ecos_get(key, "StatisticSearch", path)
    if "StatisticSearch" not in js:
        return None
    return pd.DataFrame(js["StatisticSearch"]["row"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--start", default="201501")
    ap.add_argument("--end", default="202612")
    args = ap.parse_args()
    key = get_env("ECOS_API_KEY")

    for stat in CANDIDATE_STATS:
        items = list_items(key, stat)
        if items.empty:
            continue
        if args.list:
            cols = [c for c in ["STAT_NAME", "GRP_CODE", "GRP_NAME", "ITEM_CODE", "ITEM_NAME", "CYCLE"] if c in items.columns]
            print(f"\n== {stat}")
            print(items[cols].to_string(index=False))
            continue

        if "CYCLE" in items.columns:
            items = items[items["CYCLE"].astype(str).str.contains("M")]
        if items.empty:
            continue
        groups = []
        for _, g in items.groupby("GRP_CODE", sort=True):
            if g["ITEM_NAME"].str.contains(USD_PATTERN, regex=True).any():
                g = g[g["ITEM_NAME"].str.contains(USD_PATTERN, regex=True)]
            groups.append(g["ITEM_CODE"].tolist())
        for combo in itertools.product(*groups):
            df = try_search(key, stat, list(combo), args.start, args.end)
            if df is None or df.empty:
                continue
            names = [str(df[c].iloc[0]) for c in ["ITEM_NAME1", "ITEM_NAME2", "ITEM_NAME3"]
                     if c in df.columns and pd.notna(df[c].iloc[0])]
            out = pd.DataFrame({
                "date": pd.to_datetime(df["TIME"].astype(str).str[:6], format="%Y%m"),
                "krw_per_usd": pd.to_numeric(df["DATA_VALUE"], errors="coerce"),
            }).dropna().sort_values("date").reset_index(drop=True)
            OUT.parent.mkdir(parents=True, exist_ok=True)
            out.to_parquet(OUT, index=False)
            print(f"{OUT}: {len(out)} rows, {out['date'].min():%Y-%m}..{out['date'].max():%Y-%m}, "
                  f"stat={stat} items={list(combo)} name={' / '.join(names)}, "
                  f"last={out['krw_per_usd'].iloc[-1]:.1f}")
            return
    if not args.list:
        raise SystemExit("no monthly USD series found; run with --list and share the output")


if __name__ == "__main__":
    main()
