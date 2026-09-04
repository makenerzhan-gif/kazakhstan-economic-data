import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from analysis import seasonal_targets  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]


def _real_indicators() -> dict[str, dict]:
    data = yaml.safe_load((REPO_ROOT / "config" / "indicators.yaml").read_text(encoding="utf-8"))
    return {ind["id"]: ind for ind in data["indicators"]}


def test_every_target_id_exists_in_indicators_yaml():
    ids = set(_real_indicators())
    missing = [t.indicator_id for t in seasonal_targets.SEASONAL_TARGETS if t.indicator_id not in ids]
    assert not missing, f"seasonal_targets.py references ids not in config/indicators.yaml: {missing}"


def test_targets_list_stays_curated_and_small():
    # Deliberate, human-reviewed list -- not every monthly/quarterly indicator
    # in the dataset. If this starts failing because the list grew, that
    # growth should still be a reviewed decision, not an accident.
    assert len(seasonal_targets.SEASONAL_TARGETS) <= 6


def test_every_target_has_a_rationale():
    assert all(t.rationale.strip() for t in seasonal_targets.SEASONAL_TARGETS)


def test_target_period_matches_the_indicator_real_frequency():
    indicators = _real_indicators()
    for t in seasonal_targets.SEASONAL_TARGETS:
        real_freq = indicators[t.indicator_id]["frequency"]
        expected_period = seasonal_targets.FREQUENCY_TO_PERIOD.get(real_freq)
        assert t.period == expected_period, (
            f"{t.indicator_id}: configured period={t.period} but real frequency="
            f"{real_freq!r} implies period={expected_period} -- stale config?"
        )


def test_acknowledged_lifecycle_overrides_reference_real_lifecycle_indicators():
    indicators = _real_indicators()
    lifecycle_ids = {iid for iid, ind in indicators.items() if ind.get("lifecycle")}
    for indicator_id in seasonal_targets.ACKNOWLEDGED_LIFECYCLE:
        assert indicator_id in lifecycle_ids, (
            f"{indicator_id} is in ACKNOWLEDGED_LIFECYCLE but doesn't carry a "
            f"lifecycle flag in config/indicators.yaml -- stale override?"
        )
