#!/usr/bin/env bash
# Monthly refresh: re-ingest public sources, rerun every stage, regenerate briefs.
# Ingest steps are allowed to fail (the previous processed parquet stays in place);
# the analysis stages are strict. USITC DataWeb has no public API: refresh it manually.
set -euo pipefail

python -m core_pipeline.ingest_kcs --pull || echo "kcs refresh failed, keeping previous parquet"
if [ -f data/raw/pink_sheet_monthly.xlsx ]; then
  python -m core_pipeline.ingest_lead || echo "lead refresh failed, keeping previous parquet"
else
  echo "pink sheet not downloaded, keeping previous parquet"
fi
python -m core_pipeline.ingest_fx || echo "fx refresh failed, keeping previous parquet"
python -m core_pipeline.ingest_comext || echo "comext refresh failed, keeping previous parquet"
python -m core_pipeline.ingest_parc || echo "parc refresh failed, keeping previous parquet"

python -m scripts.run_stage0
python -m scripts.run_stage1 --with-chronos
python -m scripts.run_stage2
python -m scripts.run_stage3
python -m scripts.run_stage4
python -m core_pipeline.brief
