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

## Post-hoc changes

(none)
