"""Production-function inputs (2026-09-25): Taldau breakdowns, NBK survey by sector, BNS
fixed assets and hours worked."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import update_bns  # noqa: E402
from fetchers import bns, nbk_dims, taldau_dims  # noqa: E402
from lib import validation  # noqa: E402


def test_taldau_node_values_annual_and_quarterly():
    node = {"id": "741880", "text": "РК", "y122024": "196023260237000", "122024": "1031", "y122025": "", "leaf": "false"}
    assert taldau_dims.node_values(node, "annual") == {"2024-12-31": 196023260237000.0}
    q = {"y032016": "1510437000", "y122025": "1739949300"}
    assert taldau_dims.node_values(q, "quarterly") == {"2016-01-01": 1510437000.0, "2025-10-01": 1739949300.0}


def test_nbk_survey_sectors_map_to_okved_and_reject_unknown():
    rows = [{"report_date": "2026-07-01", "amount": 57.9, "industry": "Mining",
             "indicator_code": "Capacity utilization - Weighted Average"},
            {"report_date": "2026-07-01", "amount": 50.8, "industry": "All sectors",
             "indicator_code": "Capacity utilization - Weighted Average"},
            {"report_date": "2026-07-01", "amount": 1.0, "industry": "Mining", "indicator_code": "Other"}]
    recs = nbk_dims.survey_records(rows, "Capacity utilization - Weighted Average")
    assert [(r["item_code"], r["value"]) for r in recs] == [("B", 57.9), ("TOTAL", 50.8)]
    with pytest.raises(validation.StructuralChangeError):
        nbk_dims.survey_records([{**rows[0], "industry": "Fishing"}], "Capacity utilization - Weighted Average")


def test_fixed_assets_use_the_tangible_asset_term():
    # 741881 («Всего») would add intangibles; the tangible term is 455728.
    assert bns.FIXED_ASSETS_TERMS.split(",")[bns.FIXED_ASSETS_DICS.split(",").index("77")] == "455728"
    assert bns.FIXED_ASSETS_RATIO_TERMS.split(",")[3] == "455728"


def test_new_bns_series_are_registered():
    for ind in ("FIXED_ASSETS_GROSS", "FIXED_ASSETS_NET", "FIXED_ASSETS_WEAR", "HOURS_WORKED",
                "HOURS_WORKED_QUARTERLY", "HOURS_PER_EMPLOYEE"):
        assert ind in update_bns.FETCHERS and ind in update_bns.INDICATOR_IDS
