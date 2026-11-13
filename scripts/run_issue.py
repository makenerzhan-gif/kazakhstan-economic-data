#!/usr/bin/env python3
"""The text of the GitHub issue a data run opens when something went wrong (added 2026-11-13).

    python scripts/run_issue.py <job status> <run url>   ->  prints the body, exit 0
                                                             prints nothing, exit 3: nothing to report

Read from the run's own report (reports/update_report_<today>.md): the datasets that failed
and kept their previous data, the cross-source checks that failed, and -- for context only --
the series without new observations. A run that failed as a whole is always reported, also
when it died before writing a report. Stale series alone open no issue: they are in every
report until fixed or marked `stale_ok`.
"""
from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SECTIONS = {"failed": "## Failed this run", "cross": "## Cross-source checks that failed",
            "model": "## model_data not rebuilt", "stale": "## Series with no new observations"}


def section(text: str, heading: str) -> list[str]:
    """The «- …» items under the first heading that starts with `heading`."""
    m = re.search(rf"^{re.escape(heading)}.*?$(.*?)(?=^## |\Z)", text, re.M | re.S)
    return [line for line in (m.group(1).splitlines() if m else []) if line.startswith("- ")]


def body(report_text: str | None, job_status: str, run_url: str) -> str | None:
    parts = {k: section(report_text or "", h) for k, h in SECTIONS.items()}
    job_failed = job_status != "success"
    if not job_failed and not parts["failed"] and not parts["cross"] and not parts["model"]:
        return None
    out = [f"Прогон: {run_url}", ""]
    if job_failed:
        out += [f"**Прогон завершился со статусом `{job_status}` — данные этого прогона не закоммичены.**", ""]
        if report_text is None:
            out += ["Отчёт не был записан: прогон упал до этапа отчёта. Смотрите лог шага «Run pipeline».", ""]
    for key, title in (("failed", "Не загрузились (сохранены прежние данные)"),
                       ("cross", "Не сошлись сверки двух публикаций (данные закоммичены)"),
                       ("model", "Модельный набор model_data не пересобран (оставлен прежний)"),
                       ("stale", "Для справки: ряды без новых наблюдений")):
        if parts[key]:
            shown = parts[key][:40]
            out += [f"### {title}: {len(parts[key])}", ""] + shown
            out += [f"- … и ещё {len(parts[key]) - len(shown)}"] if len(parts[key]) > len(shown) else []
            out.append("")
    return "\n".join(out).rstrip() + "\n"


def main() -> int:
    job_status, run_url = sys.argv[1], sys.argv[2]
    report = REPO_ROOT / "reports" / f"update_report_{date.today().isoformat()}.md"
    text = body(report.read_text(encoding="utf-8") if report.exists() else None, job_status, run_url)
    if text is None:
        return 3
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
