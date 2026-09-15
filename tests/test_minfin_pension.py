"""Minfin bulletin table 27 (pension contributions): the annual 1-January figures are
taken only from an edition dated 1 January; a mid-year edition is recognised and skipped."""
import io
import sys
from pathlib import Path

import openpyxl
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from fetchers import minfin  # noqa: E402
from lib import validation  # noqa: E402


def _bulletin(month: str) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "табл 27 пг"
    ws.append(["Таблица 27"])
    ws.append(["Облыстың атауы", "Поступления/ түсімдер", None, "Задолженность по ОПВ", None, "Наименование области"])
    ws.append([None, f"2025 жылдың 1 қаңтардағы /на 1 {month} 2025 года", f"2026 жылдың /на 1 {month} 2026 года",
               f"на 1 {month} 2025 года", f"на 1 {month} 2026 года", None])
    ws.append(["Ақмола облысы", 10.0, 11.0, 100.0, 110.0, "Акмолинская область"])
    ws.append(["Жиыны", 2448612.8654, 2548511.4772, 3287315.70, 4486885.77, "Итого"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_january_edition_yields_two_annual_points_per_half():
    header, total = minfin._pension_table(_bulletin("января"), "x.xlsx", "T")
    recs, months = minfin._pension_records(header, total, "first", "T")
    assert months == {"января"} and recs == [{"date": "2025-01-01", "value": 2448612.8654}, {"date": "2026-01-01", "value": 2548511.4772}]
    recs, _ = minfin._pension_records(header, total, "second", "T")
    assert recs == [{"date": "2025-01-01", "value": 3287315.70}, {"date": "2026-01-01", "value": 4486885.77}]


def test_mid_year_edition_is_recognised_by_its_month():
    header, total = minfin._pension_table(_bulletin("июля"), "x.xlsx", "T")
    _, months = minfin._pension_records(header, total, "first", "T")
    assert months == {"июля"}


def test_fetch_skips_mid_year_editions_and_uses_the_first_january_one(monkeypatch):
    docs = [{"id": 1, "title": "Statistical bulletin as of August 1, 2026", "full_text": [{"document": "/aug.xlsx"}]},
            {"id": 2, "title": "Statistical bulletin as of July 1, 2026", "full_text": [{"document": "/jul.xlsx"}]}]
    files = {"/aug.xlsx": _bulletin("июля"), "/jul.xlsx": _bulletin("января")}
    monkeypatch.setattr(minfin, "_list_documents", lambda **kw: docs)
    monkeypatch.setattr(minfin, "_download", lambda path: files[path])
    monkeypatch.setattr(minfin.raw_store, "save_raw_bytes", lambda *a, **k: None)
    monkeypatch.setattr(minfin.raw_store, "write_download_manifest", lambda *a, **k: None)
    recs, man = minfin._fetch_pension_row("first", "PENSION_CONTRIBUTIONS_RECEIVED", "note")
    assert [r["date"] for r in recs] == ["2025-01-01", "2026-01-01"] and "gov.kz-doc-2" in man["dataset_id"] and "skipped" in man["note"]
    monkeypatch.setattr(minfin, "_download", lambda path: _bulletin("июля"))
    with pytest.raises(validation.StructuralChangeError) as exc:
        minfin._fetch_pension_row("first", "PENSION_CONTRIBUTIONS_RECEIVED", "note")
    assert "dated 1 January" in str(exc.value)
