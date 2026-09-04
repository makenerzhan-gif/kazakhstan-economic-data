#!/usr/bin/env python3
"""Manually-invoked seasonal decomposition pass over the curated targets in
scripts/analysis/seasonal_targets.py. NOT wired into update_all.py or CI --
this is exploratory analysis, not a pipeline validation gate, and its output
is derived rather than sourced (see analysis/README.md).

    python scripts/decompose_seasonality.py
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analysis import decompose, seasonal_report  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    results = decompose.run_all()

    for r in results:
        print(f"{r.indicator_id}: seasonal_strength={r.seasonal_strength:.3f} (n={r.n})")

    run_date = date.today().isoformat()
    text = seasonal_report.build_report(results, run_date=run_date)

    out_dir = REPO_ROOT / "analysis" / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"seasonal_decomposition_{run_date}.md"
    out_path.write_text(text, encoding="utf-8")
    print(f"\nWrote {out_path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
