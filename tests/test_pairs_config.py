import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from analysis import pairs  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]


def _real_indicator_ids() -> set[str]:
    data = yaml.safe_load((REPO_ROOT / "config" / "indicators.yaml").read_text(encoding="utf-8"))
    return {ind["id"] for ind in data["indicators"]}


def test_every_pair_id_exists_in_indicators_yaml():
    ids = _real_indicator_ids()
    missing = [p for p in pairs.PAIRS if p.id_x not in ids or p.id_y not in ids]
    assert not missing, f"pairs.py references indicator ids not in config/indicators.yaml: {missing}"


def test_pairs_list_stays_curated_and_small():
    # This is a deliberate, human-reviewed list -- not an all-pairs matrix.
    # If this starts failing because the list grew, that growth should still
    # be a reviewed decision, not an accident.
    assert len(pairs.PAIRS) <= 10


def test_every_pair_has_a_rationale():
    assert all(p.rationale.strip() for p in pairs.PAIRS)


def test_acknowledged_lifecycle_overrides_reference_real_lifecycle_indicators():
    data = yaml.safe_load((REPO_ROOT / "config" / "indicators.yaml").read_text(encoding="utf-8"))
    lifecycle_ids = {ind["id"] for ind in data["indicators"] if ind.get("lifecycle")}
    for indicator_id in pairs.ACKNOWLEDGED_LIFECYCLE:
        assert indicator_id in lifecycle_ids, (
            f"{indicator_id} is in ACKNOWLEDGED_LIFECYCLE but doesn't carry a "
            f"lifecycle flag in config/indicators.yaml -- stale override?"
        )
