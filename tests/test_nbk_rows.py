"""NBK open-data rows: technical, uniform and per-form attribute fields must not
disqualify a fully pinned row; a real extra breakdown still must."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from fetchers import nbk  # noqa: E402
from lib import validation  # noqa: E402


def _row(**kw):
    base = {"report_date": "2026-04-01", "amount": 1.0, "type": "mln USD", "period": "Quarter",
            "account_type_code": "Current account", "instrument_type_code": " Goods and services",
            "instrument_subtype1_code": "Goods", "code": "Goods"}
    base.update(kw)
    return base


def test_row_id_added_by_the_api_on_2026_09_15_is_not_a_classification_field():
    assert "row_id" in nbk.NON_CLASSIFICATION_FIELDS
    rows = [_row(row_id="1"), _row(report_date="2026-01-01", amount=2.0, row_id="2")]
    assert nbk._bop_select(rows, "GOODS", "TEST") == {"2026-04-01": 1.0, "2026-01-01": 2.0}


def test_a_real_extra_breakdown_still_disqualifies_the_row():
    rows = [_row(row_id="1", region_code="Astana")]
    with pytest.raises(validation.StructuralChangeError):
        nbk._bop_select(rows, "GOODS", "TEST")


def _exact(monkeypatch, form_id, rows, match):
    monkeypatch.setattr(nbk, "_fetch_nbk_form_paginated", lambda f, i: rows)
    monkeypatch.setattr(nbk.raw_store, "save_raw_bytes", lambda *a, **k: None)
    monkeypatch.setattr(nbk.raw_store, "write_download_manifest", lambda *a, **k: None)
    records, _ = nbk._fetch_nbk_exact_row(form_id, match, "TEST", "note", "monthly")
    return [(r["date"], r["value"]) for r in records]


def test_exact_row_ignores_a_field_that_is_uniform_across_the_form(monkeypatch):
    rows = [{"report_date": "2026-07-01", "amount": 5.0, "currency": "US dollars", "type": "Average rate - bid", "periodicity": "monthly", "row_id": "1"},
            {"report_date": "2026-07-01", "amount": 9.0, "currency": "US dollars", "type": "Average rate - bid", "periodicity": "monthly", "residency": "resident", "row_id": "2"}]
    assert _exact(monkeypatch, "41", rows, {"currency": "US dollars", "type": "Average rate - bid"}) == [("2026-07-01", 5.0)]


def test_exact_row_ignores_the_per_form_attributes_but_not_a_varying_dimension(monkeypatch):
    kase = [{"report_date": "2026-06-30", "amount": 70.1, "type": "rate", "currency": "Euro", "period": "30 jun", "row_id": "1"},
            {"report_date": "2026-05-31", "amount": 69.5, "type": "rate", "currency": "Euro", "period": "may", "row_id": "2"}]
    assert _exact(monkeypatch, "35", kase, {"type": "rate", "currency": "Euro"}) == [("2026-05-31", 69.5), ("2026-06-30", 70.1)]
    with pytest.raises(validation.StructuralChangeError):      # the same rows under another form: `period` varies and is not ignored
        _exact(monkeypatch, "999", kase, {"type": "rate", "currency": "Euro"})


def test_remittance_counts_pin_the_total_rows():
    assert nbk.REMITTANCE_COUNT_MATCH["currency_code"] == "Total"
