#!/usr/bin/env python3
"""project_knowledge/CALENDAR.md — when each source the GDP model depends on updates next.

Three inputs: metadata/<agency>/<id>.json for every pipeline series the model contract
(config/model_map.yaml) uses — last_update_date and, for the BNS dynamic tables, the
«Дата следующей актуализации» their Метаданные sheet states; config/calendar.yaml for
the sources that publish on a fixed rhythm without a machine-readable date and for the
documents that reach the model by hand; config/manual_inputs.yaml for the refresh rule
of every hand-loaded block. Rows are sorted by the next date; a date in the past is
flagged — the source promised a release the pipeline has not yet seen.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG = REPO_ROOT / "config"
METADATA = REPO_ROOT / "metadata"
OUT = REPO_ROOT / "project_knowledge" / "CALENDAR.md"


def _load(name: str) -> dict:
    return yaml.safe_load((CONFIG / name).read_text(encoding="utf-8"))


def model_dependencies(model_map: dict, indicators: list[dict], dims: list[dict]) -> dict[str, dict]:
    """dataset id -> {agency, kind, sheets: {sheet: [mapping ids]}} for every series the contract names."""
    agency_of = {i["id"]: i["agency"] for i in indicators}
    agency_of.update({d["id"]: d["agency"] for d in dims})
    deps: dict[str, dict] = {}
    for m in model_map["mappings"]:
        ds = m.get("dims_variable") or m.get("variable")
        entry = deps.setdefault(ds, {"agency": agency_of.get(ds, "?"), "kind": "dims" if "dims_variable" in m else "scalar", "sheets": defaultdict(list)})
        sheets = [m["sheet"]] if "dims_variable" in m else [t["sheet"] for t in m["targets"]]
        for s in sheets:
            entry["sheets"][s].append(m["id"])
    return deps


def read_metadata(agency: str, dataset: str) -> dict:
    p = METADATA / agency / f"{dataset.lower()}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def build(today: date | None = None) -> str:
    today = today or date.today()
    model_map, calendar, manual = _load("model_map.yaml"), _load("calendar.yaml"), _load("manual_inputs.yaml")
    indicators = _load("indicators.yaml")["indicators"]
    dims = _load("dims.yaml")["datasets"]
    deps = model_dependencies(model_map, indicators, dims)
    rows = []
    for ds, d in deps.items():
        meta = read_metadata(d["agency"], ds)
        rows.append({"dataset": ds, "agency": d["agency"], "last": meta.get("last_update_date") or "—",
                     "published": meta.get("publication_date") or "—", "next": meta.get("next_update_date") or "",
                     "model": "; ".join(f"«{s}» ({', '.join(ids)})" for s, ids in d["sheets"].items())})
    rows.sort(key=lambda r: (r["next"] == "", r["next"], r["agency"], r["dataset"]))
    lines = [f"# Календарь обновлений модели ВВП", "", f"Сформировано {today.isoformat()} скриптом `scripts/build_calendar.py`.",
             "«Следующее обновление» для таблиц БНС — «Дата следующей актуализации» из листа Метаданные самой таблицы; "
             "для остальных источников — расписание из `config/calendar.yaml`. Дата в прошлом означает: источник обещал выпуск, "
             "которого пайплайн ещё не видел.", ""]
    overdue = [r for r in rows if r["next"] and r["next"] < today.isoformat()]
    lines += ["## Ряды пайплайна, которые читает модель", "",
              f"{len(rows)} наборов; с объявленной датой следующего обновления — {sum(1 for r in rows if r['next'])}, просрочено — {len(overdue)}.", "",
              "| Следующее обновление | Набор | Агентство | Последнее обновление (публикация) | Где в модели |", "|---|---|---|---|---|"]
    for r in rows:
        flag = " ⚠" if r["next"] and r["next"] < today.isoformat() else ""
        lines.append(f"| {r['next'] or '—'}{flag} | `{r['dataset']}` | {r['agency']} | {r['last']} ({r['published']}) | {r['model']} |")
    lines += ["", "## Источники с фиксированным ритмом и ручные документы", "", "| Ближайшая дата | Источник | Ритм | Где в модели | Действие |", "|---|---|---|---|---|"]
    for s in sorted(calendar["schedules"], key=lambda s: (str(s.get("next") or "9999"), s["id"])):
        nxt = str(s.get("next")) if s.get("next") else "—"
        flag = " ⚠" if s.get("next") and str(s["next"]) < today.isoformat() else ""
        lines.append(f"| {nxt}{flag} | {s['what']} | {s['cadence']} | {s['model']} | {s.get('action', '')} |")
    lines += ["", "## Ручные входы модели (config/manual_inputs.yaml)", "", "| Блок | Лист | Строки | Вид | Версия | Когда обновлять |", "|---|---|---|---|---|---|"]
    for e in manual["inputs"]:
        rows_txt = ", ".join(f"{r[0]}–{r[1]}" if isinstance(r, list) else str(r) for r in (e["rows"] if isinstance(e["rows"][0], list) or len(e["rows"]) != 2 or not all(isinstance(x, int) for x in e["rows"]) else [e["rows"]]))
        years = f" ({e['years'][0]}–{e['years'][1]})" if e.get("years") else ""
        lines.append(f"| `{e['id']}` | {e['sheet']} | {rows_txt}{years} | {e['kind']} | {e.get('vintage', '')} | {e.get('refresh', '')} |")
    lines += ["", "## Порядок обновления модели", ""] + [f"{i}. `{step}`" for i, step in enumerate(calendar["procedure"], 1)] + [""]
    return "\n".join(lines)


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(build(), encoding="utf-8")
    print(f"written {OUT.relative_to(REPO_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
