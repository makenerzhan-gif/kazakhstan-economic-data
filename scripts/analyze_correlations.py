#!/usr/bin/env python3
"""Manually-invoked correlation pass over the curated pairs in
scripts/analysis/pairs.py. NOT wired into update_all.py or CI -- this is
exploratory analysis, not a pipeline validation gate, and its output is
derived rather than sourced (see analysis/README.md).

    python scripts/analyze_correlations.py
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analysis import correlate, report  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    results = correlate.run_all()

    for r in results:
        r_str = f"{r.r:.3f}" if r.r is not None else "undefined"
        print(f"{r.id_x} vs {r.id_y}: r={r_str} (n={r.n})")

    run_date = date.today().isoformat()
    text = report.build_report(results, run_date=run_date)

    out_dir = REPO_ROOT / "analysis" / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"correlations_{run_date}.md"
    out_path.write_text(text, encoding="utf-8")
    print(f"\nWrote {out_path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
