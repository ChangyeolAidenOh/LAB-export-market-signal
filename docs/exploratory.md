# Exploratory analyses (post-hoc, not pre-registered)

_These were run after the pre-registered results were fixed; they inform interpretation only and are not counted as hypothesis tests._

## E1. Trend breaks (piecewise-linear PELT on STL-adjusted log kg)

**US** breaks: 2020-04, 2022-06, 2023-08

| segment | annualised slope |
|---|---|
| 2018-01 → 2020-03 | -6% |
| 2020-04 → 2022-05 | +27% |
| 2022-06 → 2023-07 | +10% |
| 2023-08 → 2026-08 | -4% |

**WORLD** breaks: 2022-06, 2023-10

| segment | annualised slope |
|---|---|
| 2018-01 → 2022-05 | +3% |
| 2022-06 → 2023-09 | +10% |
| 2023-10 → 2026-08 | -4% |

**GB** breaks: none

| segment | annualised slope |
|---|---|
| 2018-01 → 2026-08 | +3% |

Reading: the level-shift detector (pre-registered H1) found no break at the tariff; the slope detector shows whether the post-April-2025 decline is a change of trend rather than a one-off drop.

## E2. Front-loading before the April 2025 tariff (US)

Baseline: STL+ETS fit through 2025-02, forecast 2025-03..2025-09.

| date    |   actual_M |   baseline_M |   gap_M |
|:--------|-----------:|-------------:|--------:|
| 2025-03 |       27.8 |         23.6 |     4.2 |
| 2025-04 |       32.3 |         25.4 |     6.9 |
| 2025-05 |       22.5 |         23.4 |    -0.9 |
| 2025-06 |       23.1 |         22.4 |     0.7 |
| 2025-07 |       24.4 |         27.7 |    -3.3 |
| 2025-08 |       17.8 |         24.8 |    -7   |
| 2025-09 |       23.9 |         26.8 |    -2.8 |

- Excess shipments 2025-03..2025-05: **+10.2M kg ≈ +0.43 months** of the prior-12m average.
- Payback 2025-06..2025-09: -12.4M kg ≈ -0.53 months.
- If payback roughly offsets the excess, the tariff moved timing more than demand within the first half-year.

## E3. Model adoption under a relaxed coverage window

|       | strict_[0.70,0.90]   | relaxed_[0.70,0.95]   |
|:------|:---------------------|:----------------------|
| AU    | M1_stl_ets           | M1_stl_ets            |
| CA    | M2_sarima            | M3_chronos            |
| GB    | M3_chronos           | M3_chronos            |
| JP    | M1_stl_ets           | M3_chronos            |
| US    | M1_stl_ets           | M1_stl_ets            |
| WORLD | M0_snaive            | M0_snaive             |

Reading: Chronos-2 wins on point accuracy (H6) but its conformal bands sit outside the strict window on several series — over-covered (CA, JP) or under-covered (US, WORLD). Relaxing only the upper bound keeps the pre-registered rule's intent (no under-coverage) and changes which series adopt the foundation model.
