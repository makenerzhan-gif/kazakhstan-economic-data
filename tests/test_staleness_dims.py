"""The freshness check covers the item-level datasets of config/dims.yaml (added 2026-11-22: two Taldau regional
datasets had stopped at 2026-06 unnoticed)."""
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
from lib import staleness  # noqa: E402


def test_a_dims_dataset_past_its_limit_is_reported_unless_explained(tmp_path):
    for name, last in (("a_monthly", "2026-06-01"), ("b_monthly", "2026-10-01"), ("c_annual", "2019-12-31")):
        (tmp_path / f"{name}.csv").write_text(f"date,region,item_code,value\n2020-01-01,national,X,1\n{last},national,X,2\n", encoding="utf-8")
    datasets = [{"id": "A_MONTHLY", "agency": "bns", "frequency": "monthly"},
                {"id": "B_MONTHLY", "agency": "bns", "frequency": "monthly"},
                {"id": "C_ANNUAL", "agency": "bns", "frequency": "annual", "stale_ok": "historical by design"}]
    st = staleness.stale_datasets(datasets, today=date(2026, 11, 22), processed_root=tmp_path)
    assert [r["id"] for r in st] == ["C_ANNUAL", "A_MONTHLY"]
    assert [r["id"] for r in staleness.unexplained(st)] == ["A_MONTHLY"]


def test_every_stopped_dims_dataset_today_has_a_reason():
    """A new stop must be looked at: either fixed or explained with `stale_ok` in config/dims.yaml."""
    st = staleness.stale_datasets(today=date(2026, 11, 22))
    assert staleness.unexplained(st) == []
