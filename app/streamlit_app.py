"""LAB Export Market Signal — Streamlit dashboard.

Run from the repo root:  streamlit run app/streamlit_app.py
"""

import json
import os
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

from core_pipeline import brief, scenarios  # noqa: E402

P = ROOT / "data" / "processed"
TEMPLATE = "plotly_white"
C = {"actual": "#1f2937", "ma": "#2563eb", "base": "#dc2626", "band": "rgba(220,38,38,0.12)",
     "cp": "#9ca3af", "event": "#f59e0b", "bar": "#2563eb", "tn": "#dc2626", "mix": "#16a34a",
     "baseband": "rgba(37,99,235,0.12)"}
ORIGIN_COLORS = {"Korea": "#2563eb", "Mexico": "#f59e0b", "Germany": "#16a34a", "Japan": "#dc2626",
                 "Malaysia": "#7c3aed", "Vietnam": "#92400e", "China": "#db2777", "Other": "#9ca3af"}


def vline(fig, x, color, text=None, dash=None):
    fig.add_shape(type="line", x0=x, x1=x, y0=0, y1=1, xref="x", yref="paper",
                  line=dict(color=color, width=1, dash=dash))
    if text:
        fig.add_annotation(x=x, y=1.02, xref="x", yref="paper", text=text, showarrow=False,
                           font=dict(size=9, color=color))


SERIES_LABEL = {"US": "미국", "JP": "일본", "AU": "호주", "GB": "영국", "CA": "캐나다", "WORLD": "합계"}

st.set_page_config(page_title="Export Market Signal — 납축전지", layout="wide")


@st.cache_data
def load_all():
    d = {
        "series": pd.read_parquet(P / "series_monthly.parquet"),
        "fc": pd.read_parquet(P / "backtest_forecasts.parquet"),
        "scores": pd.read_parquet(P / "backtest_scores.parquet"),
        "adopted": pd.read_parquet(P / "adopted_models.parquet"),
        "cps": pd.read_parquet(P / "changepoints.parquet"),
        "pt": pd.read_parquet(P / "pass_through.parquet"),
        "origin": pd.read_parquet(P / "origin_shift.parquet"),
        "origin_m": pd.read_parquet(P / "origin_shift_monthly.parquet"),
        "events": json.load(open(ROOT / "data" / "events.json")),
        "params": json.load(open(ROOT / "data" / "scenarios.json")),
    }
    ws = P / "white_space.parquet"
    d["ws"] = pd.read_parquet(ws) if ws.exists() else None
    return d


@st.cache_data
def run_scenarios(delta, agm_share, agm_premium, lead_change):
    plan, realloc = scenarios.run(delta=delta, agm_share=agm_share, agm_premium=agm_premium, lead_change=lead_change)
    return plan, realloc


D = load_all()

st.title("납축전지(HS 8507.10) 수출 시장 신호 모니터")
st.caption("공개 무역통계(관세청·USITC·Eurostat·World Bank·한국은행) 기반 · 산업 합산 · 특정 기업 실적 아님 · Independent Project, 2026.10")

tab1, tab2 = st.tabs(["시장 신호", "2027 시나리오 시트"])

# ---------------------------------------------------------------- tab 1
with tab1:
    left, right = st.columns([3, 1])
    with right:
        sel = st.selectbox("시장", list(SERIES_LABEL), format_func=lambda k: f"{SERIES_LABEL[k]} ({k})")
        var = st.radio("변수", ["kg", "usd"], format_func=lambda v: {"kg": "수량 (kg)", "usd": "금액 (USD)"}[v])
        show_cp = st.checkbox("변화점 (PELT)", True)
        show_ev = st.checkbox("이벤트 (관세·증설)", True)
    s = D["series"][D["series"]["series"] == sel].set_index("date")
    adopted_model = D["adopted"].set_index("series").loc[sel, "model"]
    fc = D["fc"][(D["fc"]["series"] == sel) & (D["fc"]["model"] == adopted_model) & D["fc"]["is_test"] & (D["fc"]["h"] == 1)]

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=s.index, y=s[var] / 1e6, name="실적", line=dict(color=C["actual"], width=1.5)))
    fig.add_trace(go.Scatter(x=s.index, y=s[var].rolling(3).mean() / 1e6, name="3개월 이동평균", line=dict(color=C["ma"], width=1), opacity=0.8))
    if var == "kg" and not fc.empty:
        fig.add_trace(go.Scatter(x=fc["target_date"], y=fc["hi80"] / 1e6, line=dict(width=0), showlegend=False, hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=fc["target_date"], y=fc["lo80"] / 1e6, fill="tonexty", fillcolor=C["band"],
                                 line=dict(width=0), name="80% conformal 밴드"))
        fig.add_trace(go.Scatter(x=fc["target_date"], y=fc["y_hat"] / 1e6, name=f"기준선 h=1 ({adopted_model})", line=dict(color=C["base"], width=1.5)))
    if show_cp:
        for _, r in D["cps"][(D["cps"]["series"] == sel) & (D["cps"]["model"] == "l2")].iterrows():
            vline(fig, r["date"], C["cp"], dash="dot")
    if show_ev:
        for e in D["events"]["events"]:
            if e["type"] == "tariff":
                vline(fig, pd.Timestamp(e["date"]), C["event"], text=e["id"])
    fig.update_layout(template=TEMPLATE, height=420, margin=dict(l=10, r=10, t=30, b=10), yaxis_title={"kg": "백만 kg", "usd": "백만 USD"}[var],
                      legend=dict(orientation="h", y=1.08))
    with left:
        st.plotly_chart(fig, use_container_width=True)

    if var == "kg" and not fc.empty:
        gap = fc[["target_date", "y_true", "y_hat", "lo80", "hi80"]].copy()
        gap["gap_%"] = ((gap["y_true"] / gap["y_hat"] - 1) * 100).round(1)
        gap["밴드 이탈"] = ((gap["y_true"] < gap["lo80"]) | (gap["y_true"] > gap["hi80"])).map({True: "●", False: ""})
        gap["target_date"] = gap["target_date"].dt.strftime("%Y-%m")
        for c in ["y_true", "y_hat", "lo80", "hi80"]:
            gap[c] = (gap[c] / 1e6).round(1)
        gap.columns = ["월", "실적 (M kg)", "기준선", "하한80", "상한80", "갭 %", "밴드 이탈"]
        with st.expander("최근 12개월 계획(기준선) 대비 실적 갭", expanded=False):
            st.dataframe(gap, hide_index=True, use_container_width=True)
            sc = D["scores"][(D["scores"]["series"] == sel)].pivot(index="model", columns="h", values="mase").round(3)
            st.caption("백테스트 MASE (행: 모델, 열: 예측 지평)")
            st.dataframe(sc, use_container_width=True)

    if sel != "WORLD":
        try:
            md = brief.build(sel, brief._load())
            st.download_button(f"{SERIES_LABEL[sel]} 시장 브리프 (markdown)", md, file_name=f"brief_{sel}.md", mime="text/markdown")
            with st.expander("브리프 미리보기"):
                st.markdown(md)
        except Exception as e:
            st.caption(f"브리프 생성 불가: {e}")

    st.divider()
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("S1. 납값 → 수출 단가 전가율 (상위 15개 시장)")
        pt = D["pt"][(D["pt"]["target"] == "usd_per_kg") & (D["pt"]["rank"] > 0)].sort_values("cpt3", ascending=False).set_index("series")
        labels = pt["country"] if "country" in pt.columns else pt.index
        colors = [C["bar"] if p < 0.05 else C["cp"] for p in pt["cpt3_p"]]
        figb = go.Figure(go.Bar(x=labels, y=pt["cpt3"], error_y=dict(type="data", array=1.96 * pt["cpt3_se"]), marker_color=colors))
        figb.update_layout(template=TEMPLATE, height=300, margin=dict(l=10, r=10, t=10, b=10), yaxis_title="3개월 누적 전가율")
        st.plotly_chart(figb, use_container_width=True)
        t = pt[["cpt3", "cpt3_p", "cpt6", "peak_lag", "fx_beta"]].copy()
        t.index = labels
        t.columns = ["3개월 전가율", "p값", "6개월 전가율", "피크 지연(월)", "환율 계수"]
        st.dataframe(t.round(3), use_container_width=True)
        st.caption("파랑 = 유의(p<0.05), 회색 = 비유의. 유럽·중동은 분기 안에 반영, 미국·일본·동남아는 반 년 뒤에도 절반 이하. 단가는 USD/kg(믹스 포함).")
    with c2:
        st.subheader("S2. 미국 수입 원산지 전환 (HTS 8507.10.0060)")
        om = D["origin_m"]["share_val"].rolling(3).mean().dropna()
        order = [c for c in ["Korea", "Mexico", "Germany", "Japan", "Malaysia", "Vietnam", "China", "Other"] if c in om.columns]
        figa = go.Figure()
        for c in order:
            figa.add_trace(go.Scatter(x=om.index, y=om[c], name=c, stackgroup="one", mode="lines",
                                      line=dict(width=0.5, color=ORIGIN_COLORS.get(c)), fillcolor=ORIGIN_COLORS.get(c)))
        vline(figa, pd.Timestamp("2025-04-01"), C["actual"], text="E1")
        figa.update_layout(template=TEMPLATE, height=300, margin=dict(l=10, r=10, t=10, b=10), yaxis=dict(range=[0, 1], title="점유율 (금액)"),
                           legend=dict(orientation="h", y=-0.2, font=dict(size=9)))
        st.plotly_chart(figa, use_container_width=True)
        o = D["origin"][["share_val_pre", "share_val_post", "share_val_2026ytd", "delta_val_pp"]].copy()
        for c in ["share_val_pre", "share_val_post", "share_val_2026ytd"]:
            o[c] = (o[c] * 100).round(1)
        o["delta_val_pp"] = o["delta_val_pp"].round(1)
        o.columns = ["사전 12개월 %", "사후 12개월 %", "2026 YTD %", "변화 pp"]
        st.dataframe(o, use_container_width=True)
        st.caption("2025.04 관세 전후: 총수입 −15%, 중국·베트남 이탈, 독일 상승, 한국산 점유 유지.")

# ---------------------------------------------------------------- tab 2
with tab2:
    prm = D["params"]
    st.subheader("S3. 2027 시나리오 계획 시트")
    st.caption("중립 점예측이 아니라 조건부 시나리오. 아래 가정은 전부 바꿔볼 것 — 결론이 아니라 질문 목록.")
    a, b, c, d = st.columns(4)
    delta = a.slider("δ — 미국 현지생산 증분 중 한국 수출 대체 비율", 0.0, 1.0, float(prm["tennessee_ramp"]["delta_default"]), 0.1)
    agm = b.slider("2027 AGM 비중", 0.10, 0.50, float(prm["mix_shift"]["agm_share_default"]), 0.05)
    prem = c.slider("AGM 단가 프리미엄 (×)", 1.0, 2.5, float(prm["mix_shift"]["agm_premium_default"]), 0.1)
    lead = d.slider("2027 납값 변동 (log)", -0.3, 0.3, float(prm["base"]["lead_change"]), 0.05)
    plan, realloc = run_scenarios(delta, agm, prem, lead)

    ann = plan.groupby(["series", "scenario"]).agg(kg=("kg_point", "sum"), usd=("usd", "sum")).reset_index()
    ref = D["series"][D["series"]["date"].dt.year == 2025].groupby("series")[["kg", "usd"]].sum()
    tbl = ann.pivot(index="series", columns="scenario", values="kg").div(1e6).round(1)
    tbl.insert(0, "2025 실적", (ref["kg"] / 1e6).round(1))
    tbl["Base vs 2025 %"] = ((tbl["Base"] / tbl["2025 실적"] - 1) * 100).round(0)
    tbl = tbl.loc[["US", "JP", "AU", "GB", "CA", "WORLD"]]
    tbl.index = [SERIES_LABEL[i] for i in tbl.index]
    usd = ann.pivot(index="series", columns="scenario", values="usd").div(1e6).round(0).loc[["US", "JP", "AU", "GB", "CA", "WORLD"]]
    usd.index = [SERIES_LABEL[i] for i in usd.index]
    c1, c2 = st.columns(2)
    c1.markdown("**2027 수량 (백만 kg)**")
    c1.dataframe(tbl, use_container_width=True)
    c2.markdown("**2027 금액 (백만 USD)**")
    c2.dataframe(usd, use_container_width=True)

    sel2 = st.selectbox("월별 보기", ["US", "JP", "AU", "GB", "CA", "WORLD"], format_func=lambda k: SERIES_LABEL[k], key="s2")
    hist = D["series"][D["series"]["series"] == sel2].set_index("date")["kg"]
    ps = plan[plan["series"] == sel2]
    figp = go.Figure()
    figp.add_trace(go.Scatter(x=hist.index[-36:], y=hist.iloc[-36:] / 1e6, name="실적", line=dict(color=C["actual"])))
    for scn, col in [("Base", C["ma"]), ("US local production ramp", C["tn"]), ("Mix shift", C["mix"])]:
        g = ps[ps["scenario"] == scn]
        if scn == "Base":
            figp.add_trace(go.Scatter(x=g["month"], y=g["kg_hi80"] / 1e6, line=dict(width=0), showlegend=False, hoverinfo="skip"))
            figp.add_trace(go.Scatter(x=g["month"], y=g["kg_lo80"] / 1e6, fill="tonexty", fillcolor=C["baseband"], line=dict(width=0), name="80% 밴드"))
        if scn != "Mix shift":
            figp.add_trace(go.Scatter(x=g["month"], y=g["kg_point"] / 1e6, name=scn, line=dict(color=col, width=2)))
    figp.update_layout(template=TEMPLATE, height=380, margin=dict(l=10, r=10, t=10, b=10), yaxis_title="백만 kg", legend=dict(orientation="h", y=1.08))
    st.plotly_chart(figp, use_container_width=True)

    freed = realloc["freed_kg_2027"].iloc[0]
    st.markdown(f"**미국 현지생산 ramp(δ={delta:.1f})로 2027년에 비는 미국향 물량: {freed / 1e6:.1f}M kg ≈ {freed / prm['kg_per_unit'] / 1e3:.0f}천 개**")
    r = realloc.copy()
    pt = D["pt"][D["pt"]["target"] == "usd_per_kg"].set_index("series")["cpt3"]
    r["S1 전가율(3개월)"] = r["series"].map(pt).round(2)
    r["series"] = r["series"].map(SERIES_LABEL)
    r["kg_last12m"] = (r["kg_last12m"] / 1e6).round(1)
    r["kg_2027_base"] = (r["kg_2027_base"] / 1e6).round(1)
    r["yoy_growth"] = (r["yoy_growth"] * 100).round(1)
    r["freed_share_of_market"] = (r["freed_share_of_market"] * 100).round(0)
    r = r[["series", "kg_last12m", "yoy_growth", "kg_2027_base", "freed_share_of_market", "S1 전가율(3개월)"]]
    r.columns = ["시장", "최근 12개월 (M kg)", "YoY %", "2027 Base (M kg)", "비는 물량 / 시장 %", "S1 전가율(3개월)"]
    st.markdown("**재배분 후보 — 질문 목록 순서**")
    st.dataframe(r, hide_index=True, use_container_width=True)

    if D["ws"] is not None:
        st.divider()
        st.subheader("S4. 유럽 white space")
        ws = D["ws"]
        wt = st.radio("가중치", ["balanced", "demand_led", "headroom_led"], horizontal=True,
                      format_func=lambda k: {"balanced": "균형", "demand_led": "교체수요 주도", "headroom_led": "점유 여백 주도"}[k])
        show = ws.sort_values(f"score_{wt}", ascending=False)[["imports_eur_m", "kr_share", "cn_share", "growth_25_23", "agm_share_2025",
                                                               "cars_ge10_m", "share_age_ge10", f"score_{wt}", "rank_spread"]].copy()
        for c in ["kr_share", "cn_share", "growth_25_23", "agm_share_2025", "share_age_ge10"]:
            show[c] = (show[c] * 100).round(1)
        show["imports_eur_m"] = show["imports_eur_m"].round(0)
        show["cars_ge10_m"] = show["cars_ge10_m"].round(1)
        show.columns = ["수입 EUR M", "한국산 %", "중국산 %", "성장 25/23 %", "AGM 비중 %", "10년+ 차량 M", "10년+ 비중 %", "점수", "순위 변동폭"]
        c1, c2 = st.columns([1, 1])
        c1.dataframe(show.head(15), use_container_width=True)
        figs = px.scatter(ws.reset_index(), x="share_age_ge10", y="kr_share", size="cars_ge10_m", text="reporter",
                          labels={"share_age_ge10": "10년+ 차량 비중", "kr_share": "한국산 수입 점유율"}, size_max=45,
                          color_discrete_sequence=[C["ma"]], template=TEMPLATE)
        figs.update_traces(textposition="middle center", textfont_size=9, marker=dict(opacity=0.55, line=dict(width=0.5, color="#1f2937")))
        figs.update_layout(height=420, margin=dict(l=10, r=10, t=10, b=10))
        c2.plotly_chart(figs, use_container_width=True)
        st.caption("우하단(차령 높고 한국산 점유 낮음) + 큰 버블이 1차 타깃. 그리스·키프로스처럼 이미 점유가 높은 시장은 white space가 아님.")
