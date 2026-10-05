"""Pull monthly Korea export statistics (KCS, data.go.kr 15100475) for HS 8507.10.

Usage:
    python -m core_pipeline.ingest_kcs --probe
    python -m core_pipeline.ingest_kcs --pull
    python -m core_pipeline.ingest_kcs --pull --hs 850710 --start 2018 --end 2026

The API requires one country per call and a window of at most 12 months,
so the full pull loops over ISO2 country codes x years. Results are
checkpointed to a CSV so an interrupted run can resume.
"""

import argparse
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd
import pycountry
import requests

from core_pipeline.config import get_env

API_URL = "https://apis.data.go.kr/1220000/nitemtrade/getNitemtradeList"
RAW_DIR = Path("data/raw")
PROC_DIR = Path("data/processed")
CHECKPOINT = RAW_DIR / "kcs_850710_monthly.csv"
OUTPUT = PROC_DIR / "export_monthly.parquet"

FIELDS = ["year", "statCd", "statCdCntnKor1", "hsCd", "statKor", "expWgt", "expDlr", "impWgt", "impDlr"]


def get_key() -> str:
    return get_env("DATA_GO_KR_KEY")


def call(key: str, cnty: str, start: str, end: str, hs: str | None, retries: int = 3) -> list[dict]:
    params = {"serviceKey": key, "strtYymm": start, "endYymm": end, "cntyCd": cnty}
    if hs:
        params["hsSgn"] = hs
    for attempt in range(retries):
        try:
            r = requests.get(API_URL, params=params, timeout=30)
            r.raise_for_status()
            root = ET.fromstring(r.text)
            code = root.findtext(".//resultCode")
            if code not in (None, "00", "0"):
                msg = root.findtext(".//resultMsg")
                raise RuntimeError(f"{cnty} {start}-{end}: {code} {msg}")
            rows = []
            for item in root.iter("item"):
                rows.append({f: item.findtext(f) for f in FIELDS})
            return rows
        except (requests.RequestException, ET.ParseError, RuntimeError) as e:
            if attempt == retries - 1:
                print(f"skip {cnty} {start}-{end}: {e}")
                return []
            time.sleep(2 * (attempt + 1))
    return []


def probe(key: str) -> None:
    for hs in ["8507", "850710", None]:
        rows = call(key, "US", "202501", "202506", hs)
        label = hs or "(no hsSgn)"
        print(f"\n== hsSgn={label}: {len(rows)} rows")
        df = pd.DataFrame(rows)
        if not df.empty:
            cols = ["year", "statCd", "hsCd", "statKor", "expWgt", "expDlr"]
            print(df[cols].head(30).to_string(index=False))


def iso2_codes() -> list[str]:
    codes = sorted(c.alpha_2 for c in pycountry.countries)
    return [c for c in codes if c != "KR"]


def pull(key: str, hs: str, start_year: int, end_year: int, sleep: float) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROC_DIR.mkdir(parents=True, exist_ok=True)
    done = set()
    if CHECKPOINT.exists():
        prev = read_checkpoint()
        done = set(zip(prev["cnty_req"], prev["year_req"]))
    codes = iso2_codes()
    total = len(codes) * (end_year - start_year + 1)
    n = 0
    buf = []
    for cnty in codes:
        for yr in range(start_year, end_year + 1):
            n += 1
            if (cnty, str(yr)) in done:
                continue
            rows = call(key, cnty, f"{yr}01", f"{yr}12", hs)
            for r in rows:
                r["cnty_req"] = cnty
                r["year_req"] = str(yr)
            if not rows:
                rows = [{"cnty_req": cnty, "year_req": str(yr)}]
            buf.extend(rows)
            if len(buf) >= 200:
                flush(buf)
                buf = []
                print(f"{n}/{total}")
            time.sleep(sleep)
    if buf:
        flush(buf)
    build_parquet(hs)


COLS = FIELDS + ["cnty_req", "year_req"]


def flush(rows: list[dict]) -> None:
    df = pd.DataFrame(rows).reindex(columns=COLS)
    header = not CHECKPOINT.exists()
    df.to_csv(CHECKPOINT, mode="a", header=header, index=False)


def read_checkpoint() -> pd.DataFrame:
    """Read the checkpoint tolerating blocks written with either column order."""
    raw = pd.read_csv(CHECKPOINT, header=None, dtype=str, skiprows=1,
                      names=list(range(len(COLS))), keep_default_na=False)
    date_re = r"^\d{4}\.\d{2}$"
    a = raw[raw[0].str.match(date_re)]
    b = raw[raw[2].str.match(date_re)]
    a = a.set_axis(COLS, axis=1)
    b = b.set_axis(["cnty_req", "year_req"] + FIELDS, axis=1)[COLS]
    df = pd.concat([a, b], ignore_index=True)
    df = df.drop_duplicates(subset=["year", "statCd", "hsCd"])
    return df


def build_parquet(hs: str) -> None:
    df = read_checkpoint()
    df = df[df["hsCd"].astype(str).str.startswith(hs)]
    out = pd.DataFrame({
        "date": pd.to_datetime(df["year"], format="%Y.%m"),
        "country_code": df["statCd"],
        "country": df["statCdCntnKor1"],
        "hs_cd": df["hsCd"],
        "hs_name": df["statKor"],
        "exp_kg": pd.to_numeric(df["expWgt"], errors="coerce"),
        "exp_usd": pd.to_numeric(df["expDlr"], errors="coerce"),
    })
    out = out.sort_values(["country_code", "hs_cd", "date"]).reset_index(drop=True)
    out.to_parquet(OUTPUT, index=False)
    print(f"{OUTPUT}: {len(out)} rows, {out['country_code'].nunique()} countries, "
          f"{out['date'].min():%Y-%m}..{out['date'].max():%Y-%m}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--pull", action="store_true")
    ap.add_argument("--rebuild", action="store_true")
    ap.add_argument("--hs", default="850710")
    ap.add_argument("--start", type=int, default=2018)
    ap.add_argument("--end", type=int, default=2026)
    ap.add_argument("--sleep", type=float, default=0.15)
    args = ap.parse_args()
    key = get_key()
    if args.probe:
        probe(key)
    elif args.rebuild:
        build_parquet(args.hs)
    elif args.pull:
        pull(key, args.hs, args.start, args.end, args.sleep)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
