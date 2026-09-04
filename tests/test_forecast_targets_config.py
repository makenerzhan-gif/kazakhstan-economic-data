import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from analysis import forecast, forecast_targets, timeseries  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]


def _real_indicators() -> dict[str, dict]:
    data = yaml.safe_load((REPO_ROOT / "config" / "indicators.yaml").read_text(encoding="utf-8"))
    return {ind["id"]: ind for ind in data["indicators"]}


def test_every_target_id_exists_in_indicators_yaml():
    ids = set(_real_indicators())
    missing = [t.indicator_id for t in forecast_targets.FORECAST_TARGETS if t.indicator_id not in ids]
    assert not missing, f"forecast_targets.py references ids not in config/indicators.yaml: {missing}"


def test_targets_list_stays_curated_and_small():
    # Deliberate, human-reviewed list -- same 4 the decomposition pass uses,
    # not every monthly/quarterly indicator in the dataset. If this starts
    # failing because the list grew, that growth should still be a reviewed
    # decision, not an accident.
    assert len(forecast_targets.FORECAST_TARGETS) <= 6


def test_every_target_has_a_rationale():
    assert all(t.rationale.strip() for t in forecast_targets.FORECAST_TARGETS)


def test_target_period_matches_the_indicator_real_frequency():
    indicators = _real_indicators()
    for t in forecast_targets.FORECAST_TARGETS:
        real_freq = indicators[t.indicator_id]["frequency"]
        expected_period = forecast_targets.FREQUENCY_TO_PERIOD.get(real_freq)
        assert t.period == expected_period, (
            f"{t.indicator_id}: configured period={t.period} but real frequency="
            f"{real_freq!r} implies period={expected_period} -- stale config?"
        )


def test_target_horizon_matches_period_to_horizon():
    for t in forecast_targets.FORECAST_TARGETS:
        expected_horizon = forecast_targets.PERIOD_TO_HORIZON.get(t.period)
        assert t.horizon == expected_horizon, (
            f"{t.indicator_id}: configured horizon={t.horizon} but period={t.period} "
            f"implies horizon={expected_horizon} (PERIOD_TO_HORIZON) -- stale config?"
        )


def test_acknowledged_lifecycle_overrides_reference_real_lifecycle_indicators():
    indicators = _real_indicators()
    lifecycle_ids = {iid for iid, ind in indicators.items() if ind.get("lifecycle")}
    for indicator_id in forecast_targets.ACKNOWLEDGED_LIFECYCLE:
        assert indicator_id in lifecycle_ids, (
            f"{indicator_id} is in ACKNOWLEDGED_LIFECYCLE but doesn't carry a "
            f"lifecycle flag in config/indicators.yaml -- stale override?"
        )


def test_every_target_clears_the_min_cycles_floor_on_real_data():
    # Statically re-verifies the same quantity forecast.forecast_target's
    # runtime guardrail checks (post-holdout training length vs
    # MIN_CYCLES * period), against the real data on disk -- so a target
    # whose history has shrunk (a source revision, a corrected backfill)
    # is caught here, not only the next time someone happens to run the
    # script.
    long_df = timeseries.load_long()
    indicators = _real_indicators()
    for t in forecast_targets.FORECAST_TARGETS:
        meta = indicators[t.indicator_id]
        s, _ = timeseries.prepare_level(
            t.indicator_id, meta, long_df,
            acknowledged_lifecycle=forecast_targets.ACKNOWLEDGED_LIFECYCLE,
            forecast_cutoff_year=forecast_targets.FORECAST_CUTOFF_YEAR.get(t.indicator_id),
        )
        train_n = len(s) - t.horizon
        min_train_n = forecast.MIN_CYCLES * t.period
        assert train_n >= min_train_n, (
            f"{t.indicator_id}: real post-holdout training length {train_n} has "
            f"dropped below this pass's {forecast.MIN_CYCLES}x floor ({min_train_n}) -- "
            f"drop this target or shrink its horizon."
        )
