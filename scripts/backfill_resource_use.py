#!/usr/bin/env python3
"""One-off: read every xls/xlsx edition of «Ресурсы и использование отдельных видов продукции
(товаров) и сырья в Республике Казахстан» (listing 19065 and the archive listing 72035: monthly
editions from March 2019, annual ones from 2022 -- 85 files on 2026-09-27) into the processed
history of RESOURCE_USE_MONTHLY, RESOURCE_USE_YTD and RESOURCE_USE_ANNUAL.

    python scripts/backfill_resource_use.py

The daily run reads only the latest editions (fetchers/bns_resource_use.KEEP_LATEST) and lays
them over the processed history; this script supplies that history. It sets
bns_resource_use.ARCHIVE, so the editions come from every page of both listings, oldest
first, and a later edition overrides an earlier one. The editions are not copied into
data/raw. Editions published as rar (January, February and April 2019, and everything
before) are not read.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import update_dims  # noqa: E402
from fetchers import bns_resource_use  # noqa: E402
from lib import pipeline_logging  # noqa: E402

DATASETS = ("RESOURCE_USE_MONTHLY", "RESOURCE_USE_YTD", "RESOURCE_USE_ANNUAL")


def main() -> None:
    bns_resource_use.ARCHIVE = True
    log = pipeline_logging.RunLogger(run_timestamp=datetime.now().isoformat())
    update_dims.run(log, set(DATASETS))
    for e in log.entries:
        print(f"{e.dataset:24} {e.status:8} {e.records_processed or 0:7}", (e.errors or [""])[0][:200])
    print(f"{len(bns_resource_use._RUN.get('read', []))} editions read")
    if log.has_errors():
        sys.exit(1)


if __name__ == "__main__":
    main()
