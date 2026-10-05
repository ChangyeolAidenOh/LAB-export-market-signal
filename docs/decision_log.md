# Decision Log — LAB_export_market_signal

Governance: hypotheses, event dates, metrics and adoption rules below are fixed at Stage 0 close.
Anything learned afterwards goes under "Exploratory" or "Post-hoc changes" with a date and reason.

---

## Stage 0 close — 2026-10-05

### Data confirmed (file-first)

| Source | File | Coverage | Note |
|---|---|---|---|
| D1 KCS exports (data.go.kr 15100475) | data/processed/export_monthly.parquet | 2018-01..2026-08, 188 countries, HSK 8507100000 | kg and USD only, no unit count; single 10-digit code, no AGM split |
| D2 USITC General Imports HTS 8507.10 | data/processed/us_import_monthly.parquet | 2018-01..2026-07, 66 origins, 3 HTS10 codes | 8507100060 (12V >6kg) = automotive, 81% of 2025 value; units available |
| D3 World Bank Pink Sheet | data/processed/lead_price_monthly.parquet | 2015-01..2026-09 | lead USD/mt |
| D4 ECOS 731Y004 | data/processed/fx_monthly.parquet | 2015-01..2026-09 | KRW/USD monthly average (매매기준율) |

Cross-source check (US): KCS kg vs USITC units corr = 0.818 (lag 0), 0.895 (lag 1 month), 0.840 (lag 2). Implied 21.0 kg/unit. KCS USD / USITC customs value median 1.16 (KCS includes non-automotive 8507.10 subtypes). The two sources describe the same flow with ~1 month shipping lag.

### Target series (data-determined)

Top 5 destinations by 2023-2025 cumulative kg: **US (29.2%), JP (9.2%), AU (7.0%), GB (4.9%), CA (3.7%)** + World. Zero-month share 0.00 for all five.

### Decisions

| # | Decision | Reason |
|---|---|---|
| D-01 | Volume variable = kg (not units) for KCS series | KCS publishes weight only. USITC units used for US origin analysis. |
| D-02 | Unit price = USD/kg (KCS), USD/unit (USITC) | Both reported; mix caveat stated. |
| D-03 | No AGM mix analysis from data | HSK has a single 10-digit code. Mix shift stays a scenario parameter. |
| D-04 | US origin analysis uses HTS 8507100060 only | Automotive subtype; excludes motorcycle (0030) and non-12V (0090). |
| D-05 | Tariff mechanism for E1 = IEEPA reciprocal (10% -> 15%), not Section 232 auto parts | Secondary source reports 8507.10 is not on the 232 covered-parts list. Primary Annex I not verified; flagged in README. |
| D-06 | Changepoint detector = PELT only; BOCPD dropped | Does not change the result; time. |
| D-07 | Checkpoint writer fixed to a constant column order after a block-misalignment bug lost ~85% of rows on first build; repaired by rebuild without re-pull | Engineering learning: append-mode checkpoints must pin column order. |

### Disclosure — partial early look

During structural validation of the USITC file (before this log was written) the following were seen for South Korea / HTS 8507100060: a May 2025 spike in units, a lower monthly level from Sep 2025, Chinese origin share falling from ~5% to ~1%, German share rising. Hypotheses H1–H6 were written in the v1.1 plan **before** this look and are reproduced below unchanged. The pre/post windows for H2 are kept as written.

---

## Pre-registered hypotheses (fixed)

Evaluation windows: pre = 2024-04..2025-03, post = 2025-04..2026-03 unless stated.

| ID | Signal | Hypothesis | Decision rule | If rejected, report |
|---|---|---|---|---|
| H1 | B | US-bound seasonally adjusted kg series has a changepoint within E1 (2025-04) ± 2 months | PELT (l2 or rbf) detects a breakpoint in 2025-02..2025-06 | "Monthly export volume shows no clear break at the tariff; shipment-lot noise dominates" |
| H2 | S2 | After E1, US total imports (HTS 8507100060, all origins) stay within ±10% of the pre-window mean, while Korean share falls by more than 1 sd of the pre-window monthly share | Both conditions hold | Total also falls -> demand-side shock mixed in, cannot separate |
| H3 | S2 | The origin gaining the most share post-E1 is Mexico | Largest post−pre share change (pp) = Mexico | If China/Vietnam -> "low-cost substitution" reading; if Germany -> "premium/OE reallocation" reading |
| H4 | S1 | Lead-price pass-through into export unit price differs by market | Across the 5 destinations, max−min of cumulative pass-through CPT(3) > 20 pp, with HAC-significant Σβ in at least 3 markets | "Pass-through is homogeneous; pricing-power differences are not visible in unit prices" |
| H5 | S1 | Lead price contributes to value (USD) but not to volume (kg) | Σβ_k on Δlog kg not significant at 5% (HAC) | Report as-is (industry prior; not presented as a finding) |
| H6 | B | Chronos-2 zero-shot beats STL+ETS on h=1..3 MASE | M3 < M1 on at least 4 of 6 series | "ETS is sufficient for ~100-point monthly series; baseline uses ETS" (Should-have) |

Backtest protocol: rolling origin, 12 folds (origins monthly, last 12 months), horizons h = 1, 3, 6. Primary metrics MASE (vs seasonal naive) and empirical 80% coverage; secondary sMAPE and band width. Adoption: lowest mean MASE at h = 1..3 per series, subject to coverage in [0.70, 0.90].

Pass-through regression (per destination):
Δlog p_t = α + Σ_{k=0..6} β_k Δlog L_{t−k} + γ Δlog fx_t + seasonal dummies + ε_t, HAC (Newey-West, 6 lags). CPT(h) = Σ_{k≤h} β_k.

S3 and S4 are scenario/scoring outputs and are not hypothesis-tested.

---

## Exploratory (not pre-registered)

- Front-loading size: compare 2025-03..2025-05 US-bound kg against the seasonal baseline; report in months of demand pulled forward.
- Behaviour of the PELT detector in 2020 (COVID) and 2021–22 (freight) windows.
- US 2026 YTD (Jan–Aug) kg annualises to ~232M vs 278M in 2025 (−17%); attribution to tariff vs US local production is a question for S2/S3, not a finding.


---

## Stage 1–2 results — 2026-10-05

### Backbone (Stage 1)

| Series | Adopted | MASE h1–3 | cov80 |
|---|---|---|---|
| US | M1 STL+ETS | 0.866 | 0.722 |
| JP | M1 STL+ETS | 0.738 | 0.833 |
| AU | M1 STL+ETS | 0.773 | 0.722 |
| GB | M2 SARIMA | 0.899 | 0.722 |
| CA | M2 SARIMA | 1.096 | 0.861 |
| WORLD | M0 seasonal naive | 1.041 | 0.778 |

Changepoints (PELT on STL-adjusted log kg): US l2 2020-08, 2022-07, 2023-08; rbf 2020-08, 2023-08. WORLD l2/rbf 2020-06, 2022-06, 2023-09, 2025-10. GB 2025-03 (both).

### Verdicts

| ID | Verdict | Evidence |
|---|---|---|
| H1 | REJECTED | No US changepoint in 2025-02..2025-06. April 2025 is a one-month front-loading spike followed by a gradual decline, not a level shift. WORLD shows a level-down break at 2025-10. |
| H2 | REJECTED | US total imports (0060, units) post/pre = 0.847 (−15%); Korea share change = +1.3pp (−0.45 sd, i.e. up). |
| H3 | REJECTED | Largest value-share gain = Germany +3.1pp; Mexico +2.6pp. Largest losses China −4.2pp, Vietnam −3.2pp. |
| H4 | SUPPORTED | CPT(3): GB 0.87, AU 0.27, CA 0.26, US 0.21, JP 0.17 (n.s.). Spread 70pp; 4/5 HAC-significant. |
| H5 | SUPPORTED | Volume regressions insignificant in 4/5 (GB significant negative). |
| H6 | NOT TESTED | Chronos not run in Phase 1. |

### Reading (for README)

- Tariff did not create a break at the effective date; the pre-tariff shipment pull-forward and a later, gradual decline are what the data show. A level drop appears in the aggregate six months later.
- The US market shrank after the tariff; within it, low-cost origins exited and premium origins gained; Korea held share. The pre-registered "Korea loses to Mexico" story is wrong.
- Lead-price pass-through is fast and near-complete in the UK, slow and partial in the US and Japan — a market-level pricing-power difference, not a uniform cost pass-through.


---

## Stage 3–4 outputs — 2026-10-05 (scenario / scoring; not hypothesis-tested)

### S3 (defaults δ=0.6, AGM 30%, premium 1.5×, lead flat)

| Series | 2025 actual kg | 2027 Base kg | Local ramp | Base vs 2025 |
|---|---|---|---|---|
| US | 278.0M | 234.2M | 222.0M | −16% / −20% |
| JP | 84.8M | 87.3M | — | +3% |
| AU | 61.6M | 56.3M | — | −9% |
| GB | 47.8M | 55.9M | — | +17% |
| CA | 37.3M | 33.8M | — | −9% |
| WORLD | 894.0M | 827.7M | — | −7% |

Displaced Korea→US kg in 2027 at δ=0.6: 12.2M (≈0.58M units) = 22% of GB 2027 Base, 36% of CA, 14% of JP, 22% of AU.

### S4 (24 member states with age data; GR, SK, BG excluded)

Rank-stable top candidates (rank spread ≤ 2 across three weight sets): IT, FR, DE, ES, PL, CZ, PT, RO. Italy ranks 1st under all three.

### Decisions

| # | Decision | Reason |
|---|---|---|
| D-08 | 2027 band reuses h=6 conformal quantile for h>6 | No longer-horizon residuals; documented as under-coverage |
| D-09 | S4 uses value share incl. intra-EU imports | Comext WORLD partner includes EU members; Korean share is of total imports |
| D-10 | AGM share (CN 8507 10 80) reported as a market indicator, not used in S1 | 8507 10 80 includes non-AGM small types; unit price comparison unreliable |


---

## H6 and exploratory — 2026-10-05 (later the same day)

| ID | Verdict | Evidence |
|---|---|---|
| H6 | SUPPORTED | Chronos-2 zero-shot h1–3 MASE below STL+ETS on 5/6 series (JP 0.49 vs 0.74, CA 0.77 vs 1.26, GB 0.82 vs 1.28, US 0.82 vs 0.87, WORLD 0.85 vs 0.93; AU 0.91 vs 0.77). Adoption unchanged except GB because Chronos cov80 falls outside [0.70, 0.90] on CA (0.92), JP (0.94), US (0.64), WORLD (0.61). |

Pre-registered adoption rule kept as written. Relaxed-window alternative recorded under exploratory E3, not applied.

### Exploratory (dated 2026-10-05; see docs/exploratory.md)

- E1: piecewise-linear PELT — US slope −4%/yr from 2023-08 with no break in 2025; WORLD −4%/yr from 2023-10. The decline predates the tariff by ~20 months and coincides with the first US local-production capacity.
- E2: front-loading 2025-03..05 = +10.2M kg (+0.43 months), payback 2025-06..09 = −12.4M kg (−0.53 months).
- E3: coverage window [0.70, 0.95] would adopt Chronos-2 for CA and JP as well.

### Decisions

| # | Decision | Reason |
|---|---|---|
| D-11 | 2027 base forecast is fitted locally with the adopted model (incl. Chronos-2) and saved; the dashboard only applies scenario arithmetic | Streamlit Cloud memory; local result preserved exactly |
| D-12 | S1 extended to top-15 destinations for the pass-through map; H4/H5 verdicts remain on the pre-registered top-5 | Richer signal without changing the test |
| D-13 | Market briefs generated from parquet with rule-based questions; no LLM | Reproducible, no cost, every sentence traceable to a number |
