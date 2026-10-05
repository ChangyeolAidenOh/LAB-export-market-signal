"""Market brief generator: one markdown page per destination for a customer meeting.

Usage:
    python -m core_pipeline.brief            # all target markets -> docs/briefs/<series>.md
    python -m core_pipeline.brief --series GB

Sections: 1) baseline vs actual, 2) pricing (lead pass-through), 3) US origin context (US only),
4) 2027 scenario numbers, 5) three questions to ask the customer. Everything is read from parquet.
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

P = Path("data/processed")
OUT = Path("docs/briefs")
LABEL = {"US": "미국", "JP": "일본", "AU": "호주", "GB": "영국", "CA": "캐나다", "WORLD": "합계"}


def _load():
    d = {
        "series": pd.read_parquet(P / "series_monthly.parquet"),
        "fc": pd.read_parquet(P / "backtest_forecasts.parquet"),
        "scores": pd.read_parquet(P / "backtest_scores.parquet"),
        "adopted": pd.read_parquet(P / "adopted_models.parquet").set_index("series"),
        "cps": pd.read_parquet(P / "changepoints.parquet"),
        "pt": pd.read_parquet(P / "pass_through.parquet"),
        "plan": pd.read_parquet(P / "plan_2027.parquet"),
        "realloc": pd.read_parquet(P / "reallocation_2027.parquet"),
        "events": json.load(open("data/events.json")),
    }
    o = P / "origin_shift.parquet"
    d["origin"] = pd.read_parquet(o) if o.exists() else None
    return d


def _m(x, unit="M kg"):
    return f"{x / 1e6:,.1f}{unit}"


def _pt_label(cpt3: float) -> str:
    if cpt3 >= 0.6:
        return "한 분기 안에 대부분 반영되는 스팟·AM 성격"
    if cpt3 >= 0.3:
        return "분기 내 일부 반영, 반기에 절반 이상 반영"
    return "반기가 지나도 절반 이하만 반영되는 계약·OE 성격"


def build(series: str, d: dict) -> str:
    s = d["series"][d["series"]["series"] == series].set_index("date")
    last = s.index[-1]
    y = s["kg"]
    l12, p12 = y.iloc[-12:].sum(), y.iloc[-24:-12].sum()
    yoy = l12 / p12 - 1
    model = d["adopted"].loc[series, "model"]
    fc = d["fc"][(d["fc"]["series"] == series) & (d["fc"]["model"] == model) & d["fc"]["is_test"] & (d["fc"]["h"] == 1)]
    gap = fc["y_true"] / fc["y_hat"] - 1
    out_of_band = fc[(fc["y_true"] < fc["lo80"]) | (fc["y_true"] > fc["hi80"])]
    sc = d["scores"][(d["scores"]["series"] == series) & (d["scores"]["model"] == model) & (d["scores"]["h"] <= 3)]
    pt = d["pt"][(d["pt"]["target"] == "usd_per_kg") & (d["pt"]["series"] == series)]
    ptr = pt.iloc[0] if not pt.empty else None
    pt_all = d["pt"][(d["pt"]["target"] == "usd_per_kg") & (d["pt"]["rank"] > 0)].sort_values("cpt3", ascending=False)
    rank_pt = int((pt_all["series"] == series).to_numpy().argmax()) + 1 if series in pt_all["series"].values else None
    plan = d["plan"][d["plan"]["series"] == series]
    base27 = plan[plan["scenario"] == "Base"]["kg_point"].sum()
    lo27 = plan[plan["scenario"] == "Base"]["kg_lo80"].sum()
    hi27 = plan[plan["scenario"] == "Base"]["kg_hi80"].sum()
    y2025 = y[y.index.year == 2025].sum()
    cps = d["cps"][(d["cps"]["series"] == series) & (d["cps"]["model"] == "l2")]["date"].dt.strftime("%Y-%m").tolist()
    price_last = s["usd_per_kg"].iloc[-12:].mean()
    price_prev = s["usd_per_kg"].iloc[-24:-12].mean()

    lines = [f"# {LABEL.get(series, series)} ({series}) — 시장 브리프", "",
             f"_기준: 한국 수출 HS 8507.10, 관세청 월별 통계 {last:%Y-%m}까지 · 산업 합산 · 생성일 {pd.Timestamp.today():%Y-%m-%d}_", "",
             "## 1. 물량 — 기준선 대비 어디에 있나", "",
             f"- 최근 12개월 {_m(l12)} (전년 동기 대비 {yoy:+.1%}). 2025년 {_m(y2025)}.",
             f"- 기준선 모델 {model}, 1~3개월 MASE {sc['mase'].mean():.2f} (1 미만이면 계절 naive보다 정확), 80% 밴드 적중률 {sc['cov80'].mean():.0%}.",
             f"- 최근 12개월 중 기준선 대비 평균 갭 {gap.mean():+.1%}, 밴드 이탈 {len(out_of_band)}개월"
             + (f" ({', '.join(out_of_band['target_date'].dt.strftime('%Y-%m'))})" if len(out_of_band) else "") + ".",
             f"- 구조 변화점(PELT): {', '.join(cps) if cps else '없음'}.", "",
             "## 2. 가격 — 납값이 단가에 얼마나 빨리 들어오나", ""]
    if ptr is not None:
        lines += [f"- 3개월 누적 전가율 {ptr['cpt3']:.2f} (p={ptr['cpt3_p']:.3f}), 6개월 {ptr['cpt6']:.2f}, 피크 지연 {int(ptr['peak_lag'])}개월"
                  + (f" — 상위 15개 시장 중 {rank_pt}위" if rank_pt else "") + ".",
                  f"- 해석: {_pt_label(ptr['cpt3'])}. 환율 계수 {ptr['fx_beta']:+.2f} (원화 약세 10% → USD 단가 {ptr['fx_beta'] * 10:+.1f}%).",
                  f"- 최근 12개월 평균 단가 {price_last:.2f} USD/kg (전년 {price_prev:.2f}, {price_last / price_prev - 1:+.1%}). 믹스 포함 단가임."]
    else:
        lines += ["- 전가율 추정 없음(시계열 길이 부족)."]
    lines += [""]
    n = 3
    if series == "US" and d["origin"] is not None:
        o = d["origin"]
        lines += [f"## {n}. 경쟁 — 관세 이후 미국 수입 원산지 (HTS 8507.10.0060)", ""]
        n += 1
        for org in ["Korea", "Mexico", "Germany", "China", "Vietnam"]:
            if org in o.index:
                r = o.loc[org]
                lines.append(f"- {org}: {r['share_val_pre'] * 100:.1f}% → {r['share_val_post'] * 100:.1f}% ({r['delta_val_pp']:+.1f}pp), 2026 YTD {r['share_val_2026ytd'] * 100:.1f}%")
        lines += ["- 총수입 −15%, 저가 원산지 이탈·프리미엄 상승, 한국산 점유 유지.", ""]
    lines += [f"## {n}. 2027 — 시나리오 시트 (조건부, 결론 아님)", "",
              f"- Base: {_m(base27)} (80% 밴드 {_m(lo27)}~{_m(hi27)}), 2025 대비 {base27 / y2025 - 1:+.0%}."]
    if series == "US":
        tn = plan[plan["scenario"] == "Local ramp"]
        freed = tn["displaced_kg"].sum()
        lines.append(f"- Local ramp(δ={d['realloc']['delta'].iloc[0]}): {_m(tn['kg_point'].sum())}, 비는 물량 {_m(freed)} ≈ {freed / 21 / 1e3:,.0f}천 개.")
    else:
        rr = d["realloc"][d["realloc"]["series"] == series]
        if not rr.empty:
            lines.append(f"- 미국향에서 비는 물량이 이 시장 2027 Base의 {rr['freed_share_of_market'].iloc[0]:.0%} 규모 — 재배분 후보 검토 대상.")
    mix = plan[plan["scenario"] == "Mix shift"]["usd"].sum()
    basev = plan[plan["scenario"] == "Base"]["usd"].sum()
    lines += [f"- Mix shift(AGM 비중 상향): 금액 {_m(basev, 'M USD')} → {_m(mix, 'M USD')} ({mix / basev - 1:+.1%}).", "",
              f"## {n + 1}. 거래선에 물어볼 질문 3개", ""]
    qs = []
    if ptr is not None and ptr["cpt3"] >= 0.6:
        qs.append("납값 연동 조항의 반영 주기가 분기인가, 월인가 — 통계는 분기 안에 대부분 반영됨을 보여주는데 실제 계약과 맞는가.")
    elif ptr is not None:
        qs.append("납값 상승분이 단가에 들어오기까지 반 년 이상 걸리는 구조인데, 그 사이 마진은 누가 흡수하고 있는가.")
    if len(out_of_band):
        qs.append(f"{out_of_band['target_date'].dt.strftime('%Y-%m').iloc[-1]}의 밴드 이탈이 거래선 재고 조정인가, 최종 수요 변화인가.")
    else:
        qs.append("최근 12개월이 기준선 밴드 안에 있는데, 거래선 쪽 재고 수준도 평년 범위인가.")
    if series == "US":
        qs.append("현지 생산 전환 후 한국 수출분이 어느 거래선·제품군(AGM/EFB)에 남는가.")
    elif yoy > 0.05:
        qs.append("최근 12개월 성장이 신규 거래선 확대인가, 기존 거래선 sell-out 증가인가 — 2027 재배분 물량을 받을 여력이 있는가.")
    else:
        qs.append("역성장 구간에서 경쟁 원산지(중국·현지 브랜드)의 가격 포지션이 어떻게 바뀌었는가.")
    lines += [f"{i + 1}. {q}" for i, q in enumerate(qs[:3])]
    lines += ["", "---", "_Evidence: 물량·경쟁은 Observed(원자료 계산), 가격은 Inferred(회귀), 2027은 Proposed(시나리오). 특정 기업 실적이 아닌 산업 합산 통계._"]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--series", default=None)
    args = ap.parse_args()
    d = _load()
    OUT.mkdir(parents=True, exist_ok=True)
    targets = [args.series] if args.series else ["US", "JP", "AU", "GB", "CA"]
    for s in targets:
        md = build(s, d)
        (OUT / f"{s}.md").write_text(md, encoding="utf-8")
        print(f"{OUT / f'{s}.md'}: {len(md.splitlines())} lines")


if __name__ == "__main__":
    main()
