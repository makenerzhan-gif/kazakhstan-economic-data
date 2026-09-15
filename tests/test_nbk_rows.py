"""NBK open-data rows: technical fields must not disqualify a fully pinned row."""
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
