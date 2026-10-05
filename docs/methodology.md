# Methodology

## 데이터

| 소스 | 변수 | 처리 |
|---|---|---|
| 관세청 품목별 국가별 수출입실적 (API 15100475) | HSK 8507100000, 국가·월별 수출 중량(kg)·금액(USD) | 국가 248개 × 연도 루프, 체크포인트 CSV(컬럼 순서 고정), 상위 5개국 + 합계 |
| USITC DataWeb General Imports | HTS 8507.10.00 10단위, 원산지·월별 customs value·first unit of quantity(개) | 0060(12V, >6kg)만 자동차용으로 사용 |
| World Bank Pink Sheet | 납 USD/mt 월평균 | — |
| ECOS 731Y004 | 원/달러 매매기준율 월평균 | — |
| Eurostat Comext DS-045409 | CN 85071020/85071080, EU27 reporter × KR·CN·WORLD, 월별 EUR·100kg·개수 | JSON-stat 엔드포인트, reporter별 호출 |
| Eurostat road_eqs_carage | 연령대별 승용차 대수 | 10년+ = Y10-20 + Y_GT20, 연령 분해가 있는 최신 연도 |

교차검증: 미국향 관세청 kg vs USITC 한국산 개수 — 상관 0.818(lag 0), 0.895(lag 1), 0.840(lag 2). 개당 21.0kg. 관세청 USD / USITC customs value 중앙값 1.16 (관세청은 8507.10 전체, USITC는 0060만).

## 백본

- 변환: log1p(kg).
- M0 계절 naive (lag 12). M1 STL(period 12, robust) + ETS(additive, damped trend). M2 SARIMA(1,1,1)(0,1,1)12. M3 Chronos-2 zero-shot (선택, context 60).
- 백테스트: 롤링 오리진 24개(캘리브레이션 12 + 테스트 12), 지평 1~6. 마지막 오리진은 h=6이 관측되는 최신 월.
- Conformal: 테스트 폴드 k의 지평 h 밴드 = 이전 모든 폴드의 |log 잔차| 경험 분위수(0.8, 0.95). 최소 6개 잔차 이후 적용.
- 지표: MASE(분모 = 학습 구간 계절 naive 평균 절대오차), sMAPE, 80/95% 경험 coverage, 밴드 폭/실적.
- 채택: 지평 1~3 평균 MASE 최소, cov80 ∈ [0.70, 0.90]. 조건 충족 모델이 없으면 MASE 최소.
- 변화점: STL 계절조정(trend + resid) 계열에 PELT. l2 penalty = 2·log(n)·Var(Δx), rbf penalty = 3 (표준화 후), min_size 3.

## S1 전가율

국가별 분포 지연 회귀:

    Δlog p_t = α + Σ_{k=0..6} β_k Δlog L_{t−k} + γ Δlog fx_t + 월 더미 + ε_t

p = USD/kg, L = 납 USD/mt, fx = KRW/USD. HAC(Newey-West, 6 lags). CPT(h) = Σ_{k≤h} β_k, 표준오차는 공분산 행렬로 계산. 동일 설계로 Δlog kg 회귀(H5).
교란: 단가는 사이즈·AGM 믹스를 포함. Δlog로 추세 제거, 믹스 통제 변수 없음.

## S2 원산지 전환

HTS 8507100060, 금액·개수 점유율. 사전 2024.04–2025.03, 사후 2025.04–2026.03, 2026 YTD. H2 판정은 개수 기준 총수입 비율과 한국산 개수 점유율의 사전 월별 표준편차.

## S3 2027 시나리오

- Base: 채택 모델을 전체 이력으로 재적합, 2027.12까지 예측. 밴드는 백테스트 잔차 분위수를 지평별로 재사용(h>6은 h=6). 단가 = 최근 12개월 USD/kg × exp(CPT(6) × 납값 가정).
- Local ramp: 미국향에서 δ × 160만대 × 21kg / 12 × ramp(t)를 차감. ramp는 2026.10→2027.12 선형.
- Mix shift: 단가 × (1 + a₁(m−1)) / (1 + a₀(m−1)), a₀ = 0.20.
- 재배분 후보: 비는 kg / 비미국 시장 2027 Base kg.

## S4 white space

점수 = Σ wᵢ·z(componentᵢ), 0–100 정규화.
demand = log(10년+ 차량 수), market = log(수입 EUR, 24–25 평균), headroom = 1 − 한국산 점유율, growth = 수입 성장 25/23 (−0.5~1.0 클립).
가중치: 균형(0.35/0.35/0.20/0.10), 교체수요 주도(0.50/0.25/0.15/0.10), 점유여백 주도(0.25/0.25/0.40/0.10). 순위 변동폭 ≤2를 안정 후보로 표시.
한계: 수입에 역내(EU) 교역 포함. 그리스·슬로바키아·불가리아는 연령 데이터 부재로 제외.

## 사전 등록과 사후 탐색

가설 H1~H6, 이벤트 캘린더, 평가 규칙은 Stage 0 종료 시 커밋(`docs/decision_log.md`). 구조 검증 중 USITC 한국 행 일부를 선행 확인한 사실은 decision_log에 공개. 사후 탐색은 별도 섹션에 날짜와 함께 기록.
