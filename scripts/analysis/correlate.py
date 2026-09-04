"""Pairwise correlation pass over the unified dataset.

Reads data/unified/macro_long.csv only -- never data/processed/ or data/raw/
directly. Every output is DERIVED, not sourced; see analysis/README.md.
Writes nothing to data/, config/, or project_knowledge/.

Callers (scripts/analyze_correlations.py, tests/test_correlate.py) are
responsible for putting scripts/ on sys.path before importing this module,
same convention as scripts/lib/*.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import yaml

from lib import periods, transformations  # noqa: E402

from . import pairs as pairs_config

REPO_ROOT = Path(__file__).resolve().parents[2]
UNIFIED_LONG = REPO_ROOT / "data" / "unified" / "macro_long.csv"
INDICATORS_YAML = REPO_ROOT / "config" / "indicators.yaml"
FREQUENCY_YAML = REPO_ROOT / "config" / "frequency.yaml"

RESAMPLE_OFFSET = {"monthly": "MS", "quarterly": "QS", "annual": "AS"}


class AnalysisGuardrailError(Exception):
    """Mirrors validation.StructuralChangeError's stop-loudly philosophy: raised
    when a pair would violate a data-integrity rule rather than silently
    guessing.
    """


@dataclass
class PairResult:
    id_x: str
    id_y: str
    label: str
    rationale: str
    interpretation: str
    transform_x: str
    transform_y: str
    n: int
    date_start: str | None
    date_end: str | None
    r: float | None
    caveats: list[str] = field(default_factory=list)


def load_indicators(path: Path = INDICATORS_YAML) -> dict[str, dict]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))["indicators"]
    return {ind["id"]: ind for ind in data}


def load_long(path: Path = UNIFIED_LONG) -> pd.DataFrame:
    return pd.read_csv(path, dtype={"date": str, "variable": str})


def load_aggregation_methods(path: Path = FREQUENCY_YAML) -> dict[str, str]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data.get("indicator_aggregation", {}) or {}


def _series_for(long_df: pd.DataFrame, indicator_id: str) -> pd.Series:
    """Raw (date -> value) for one indicator, sorted ascending, NaNs dropped."""
    rows = long_df.loc[long_df["variable"] == indicator_id, ["date", "value"]].dropna()
    if rows.empty:
        raise AnalysisGuardrailError(f"{indicator_id}: no data rows in {UNIFIED_LONG.name}")
    idx = pd.to_datetime(rows["date"])
    s = pd.Series(rows["value"].to_numpy(dtype=float), index=idx, name=indicator_id)
    return s.sort_index()


def _to_transform_series(s: pd.Series) -> transformations.Series:
    return [(d.strftime("%Y-%m-%d"), (None if pd.isna(v) else float(v))) for d, v in s.items()]


def _from_transform_series(rows: transformations.Series, name: str) -> pd.Series:
    dates = pd.to_datetime([d for d, _ in rows])
    values = [v if v is not None else float("nan") for _, v in rows]
    return pd.Series(values, index=dates, name=name)


def prepare_indicator(
    indicator_id: str,
    meta: dict,
    long_df: pd.DataFrame,
    *,
    resample_to: str | None = None,
    forecast_cutoff_year: int | None = None,
) -> tuple[pd.Series, str]:
    """Decumulate (if YTD) -> forecast cutoff (if an IMF projection series) ->
    resample (if requested and native frequency differs) -> AS-IS if already a
    published comparison, else period-over-period % change.

    Returns (prepared series, human-readable description of what was done --
    goes straight into the report so a reader sees exactly what happened to
    each side of a pair, not just the final number).
    """
    if meta.get("lifecycle") and indicator_id not in pairs_config.ACKNOWLEDGED_LIFECYCLE:
        raise AnalysisGuardrailError(
            f"{indicator_id}: carries lifecycle={meta['lifecycle']!r} (a known structural "
            f"break in its history) and is not in pairs.ACKNOWLEDGED_LIFECYCLE. Add it "
            f"there with a note on why it's still safe to use for this pair, or leave the "
            f"pair out."
        )

    s = _series_for(long_df, indicator_id)
    steps: list[str] = []

    if meta.get("category") == "international_projection":
        if forecast_cutoff_year is None:
            raise AnalysisGuardrailError(
                f"{indicator_id}: category=international_projection -- this series bakes "
                f"IMF WEO forecast years into the same column as historical actuals. Set "
                f"pairs.FORECAST_CUTOFF_YEAR[{indicator_id!r}] = <last actual year> before "
                f"using it, or leave this pair out."
            )
        s = s[s.index.year <= forecast_cutoff_year]
        steps.append(f"actuals through {forecast_cutoff_year} (WEO forecast years excluded)")

    if meta.get("cumulation") == "year_to_date":
        s = _from_transform_series(
            transformations.decumulate_ytd(_to_transform_series(s)), indicator_id
        )
        steps.append("de-cumulated (year-to-date total -> own-period contribution)")

    native_freq = meta.get("frequency")
    if resample_to and resample_to != native_freq:
        method = load_aggregation_methods().get(indicator_id)
        if not method:
            raise AnalysisGuardrailError(
                f"{indicator_id}: needs resampling {native_freq} -> {resample_to} but has "
                f"no entry in config/frequency.yaml's indicator_aggregation -- add one "
                f"there rather than guessing a method here."
            )
        offset = RESAMPLE_OFFSET.get(resample_to)
        if offset is None:
            raise AnalysisGuardrailError(f"No resample offset known for frequency {resample_to!r}.")
        resampler = s.resample(offset)
        if method == "mean":
            s = resampler.mean()
        elif method == "sum":
            s = resampler.sum()
        elif method == "end_of_period":
            s = resampler.last()
        else:
            raise AnalysisGuardrailError(
                f"{indicator_id}: aggregation method {method!r} from frequency.yaml is not "
                f"implemented in this analysis pass (only mean/sum/end_of_period are)."
            )
        s = s.dropna()
        steps.append(f"resampled {native_freq} -> {resample_to} ({method}, per config/frequency.yaml)")

    if meta.get("observation_type") == "comparison_index":
        steps.append("used as-is (already a published comparison)")
    else:
        s = _from_transform_series(
            transformations.growth_rate(_to_transform_series(s), periods=1), indicator_id
        ).dropna()
        steps.append("period-over-period % change (transformations.growth_rate)")

    return s, "; ".join(steps)


def check_consistent_annual_convention(id_x: str, dates_x, id_y: str, dates_y) -> None:
    """Only meaningful when both sides are annual. Raises if the two series
    settle on different singleton conventions (start vs end) -- the landmine
    documented in lib/periods.py's module docstring: annual dates are
    deliberately never normalised, so two annual series can silently anchor
    to different points in the year.
    """
    conv_x = {periods.convention_of(d, "annual") for d in dates_x} - {"other"}
    conv_y = {periods.convention_of(d, "annual") for d in dates_y} - {"other"}
    if len(conv_x) == 1 and len(conv_y) == 1 and conv_x != conv_y:
        raise AnalysisGuardrailError(
            f"{id_x} dates its annual observations at period-{next(iter(conv_x))} while "
            f"{id_y} dates them at period-{next(iter(conv_y))} -- joining them on date "
            f"would silently compare the wrong year-anchor. See scripts/lib/periods.py."
        )


def correlate_pair(
    pair: pairs_config.Pair, long_df: pd.DataFrame, indicators_by_id: dict[str, dict]
) -> PairResult:
    meta_x = indicators_by_id[pair.id_x]
    meta_y = indicators_by_id[pair.id_y]

    if meta_x.get("frequency") == "annual" and meta_y.get("frequency") == "annual":
        raw_x = long_df.loc[long_df["variable"] == pair.id_x, "date"]
        raw_y = long_df.loc[long_df["variable"] == pair.id_y, "date"]
        check_consistent_annual_convention(pair.id_x, raw_x, pair.id_y, raw_y)

    x, transform_x = prepare_indicator(
        pair.id_x, meta_x, long_df, resample_to=pair.resample_to,
        forecast_cutoff_year=pairs_config.FORECAST_CUTOFF_YEAR.get(pair.id_x),
    )
    y, transform_y = prepare_indicator(
        pair.id_y, meta_y, long_df, resample_to=pair.resample_to,
        forecast_cutoff_year=pairs_config.FORECAST_CUTOFF_YEAR.get(pair.id_y),
    )

    joined = pd.concat([x, y], axis=1, keys=[pair.id_x, pair.id_y]).dropna()
    n = len(joined)
    r = joined[pair.id_x].corr(joined[pair.id_y]) if n >= 2 else None
    date_start = joined.index.min().strftime("%Y-%m-%d") if n else None
    date_end = joined.index.max().strftime("%Y-%m-%d") if n else None

    caveats: list[str] = []
    if r is not None and pd.isna(r):
        caveats.append("correlation is undefined (a constant series after transform).")
        r = None
    if n < 30:
        caveats.append(f"n={n} -- small sample; treat as descriptive, not confirmatory.")

    return PairResult(
        id_x=pair.id_x, id_y=pair.id_y, label=pair.label, rationale=pair.rationale,
        interpretation=pair.interpretation, transform_x=transform_x, transform_y=transform_y,
        n=n, date_start=date_start, date_end=date_end, r=r, caveats=caveats,
    )


def run_all(pair_list: list[pairs_config.Pair] | None = None) -> list[PairResult]:
    pair_list = pairs_config.PAIRS if pair_list is None else pair_list
    long_df = load_long()
    indicators_by_id = load_indicators()
    return [correlate_pair(p, long_df, indicators_by_id) for p in pair_list]
