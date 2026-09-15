"""model_coverage (every literal number is claimed by the pipeline contract or by
manual_inputs.yaml), the BNS update-date extraction and the calendar builder."""
import sys
from datetime import date
from pathlib import Path

import openpyxl
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_calendar  # noqa: E402
import model_coverage  # noqa: E402
from fetchers import bns_dims  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]


def _workbook(tmp_path: Path) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Факторы"
    ws.append(["Показатель", 2022, 2023, 2024, 2025, 2026])
    ws.append(["Brent", 99.8, 82.6, 80.7, 69.0, "=E2*1.1"])            # row 2: numbers + a formula
    ws.append(["Консенсус", 97.0, 83.8, 84.1, 74.7, 79.6])              # row 3: all numbers
    ws.append(["Код ОКЭД", 2022, 2023, 2024, 2025, 2026])               # row 4: a repeated year header
    ws.append(["Текст", "a", "b", None, True, 5.0])                     # row 5: only F5 is a number
    wb.create_sheet("Лист2").append(["x", 1.0, 2.0])
    p = tmp_path / "model.xlsx"
    wb.save(p)
    return p


CFG = {"model": {"year_header_row": 1, "default_years": [2023, 2024, 2025]},
       "mappings": [{"id": "brent", "variable": "OIL_PRICE_BRENT", "targets": [{"sheet": "Факторы", "row": 2}]}]}


def test_coverage_classifies_pipeline_manual_and_unaccounted(tmp_path):
    manual = {"inputs": [{"id": "consensus", "sheet": "Факторы", "rows": [3], "years": [2022, 2030]},
                         {"id": "io", "sheet": "Лист2", "rows": [1, 10], "columns": ["A", "C"]}]}
    cells = model_coverage.scan(_workbook(tmp_path), CFG, manual)
    by = {(c.sheet, c.row, c.year): c.status for c in cells}
    assert by[("Факторы", 2, 2023)] == "pipeline" and by[("Факторы", 2, 2025)] == "pipeline"
    assert by[("Факторы", 2, 2022)] == "unaccounted"          # outside the mapping's years
    assert ("Факторы", 2, 2026) not in by                      # a formula is not a literal number
    assert all(by[("Факторы", 3, y)] == "manual" for y in (2022, 2023, 2026))
    assert not any(c.row == 4 for c in cells)                  # repeated year header ignored
    assert by[("Факторы", 5, 2026)] == "unaccounted" and sum(1 for c in cells if c.row == 5) == 1   # True and text are not numbers
    assert {c.status for c in cells if c.sheet == "Лист2"} == {"manual"}
    text = model_coverage.report(cells)
    assert "unaccounted rows: 2" in text and "TOTAL" in text


def test_manual_inputs_file_is_well_formed():
    manual = yaml.safe_load((REPO_ROOT / "config" / "manual_inputs.yaml").read_text(encoding="utf-8"))
    ids = [e["id"] for e in manual["inputs"]]
    assert len(ids) == len(set(ids))
    for e in manual["inputs"]:
        assert e["kind"] in ("history", "assumption", "external", "satellite", "review"), e["id"]
        assert e["sheet"] and e["rows"] and e["source"] and e.get("vintage") and e.get("owner") and e.get("refresh") is not None, e["id"]
        if e.get("years"):
            assert len(e["years"]) == 2 and e["years"][0] <= e["years"][1], e["id"]


def test_bns_update_dates_are_read_from_the_metadata_sheet():
    grids = {"Метаданные": [["Код статистического показателя", "111203"], ["Дата последней актуализации:  ", "2026-08-14 00:00:00"],
                            ["Дата следующей актуализации:", None, "30.09.2026"], ["Примечание", "x"]],
             "2010-2026": [["a", 1]]}
    assert bns_dims.update_dates(grids) == {"release": "2026-08-14", "next_update": "2026-09-30"}
    assert bns_dims.update_dates({"Лист1": [["no metadata"]]}) == {}


def test_calendar_lists_model_dependencies_and_flags_overdue_dates():
    text = build_calendar.build(today=date(2026, 9, 15))
    assert "GVA_NOMINAL_BY_SECTION" in text and "WB_COMMODITY_PRICES_ANNUAL" in text
    assert "2026-10-02" in text                                   # the announced CMO release
    assert "## Порядок обновления модели" in text and "model_coverage.py --strict" in text
    late = build_calendar.build(today=date(2027, 12, 31))
    assert "⚠" in late                                            # every announced date is then in the past
