"""Post-download validation.

Design intent (MASTER TASK section 6): checks run after every update. Any
structural change in the source (new/missing columns, unit change, frequency
change) must STOP the pipeline loudly rather than silently coercing the data.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


class StructuralChangeError(Exception):
    """Raised when the source's structure no longer matches what we expect.

    Callers must present WHAT CHANGED / EXPECTED / ACTUAL / ACTION REQUIRED
    and stop processing that dataset — never continue silently.
    """


@dataclass
class ValidationResult:
    indicator_id: str
    ok: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add_error(self, msg: str) -> None:
        self.ok = False
        self.errors.append(msg)

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)


EXPECTED_COLUMNS = {"date", "value"}
FREQUENCY_DELTA_DAYS = {
    "daily": (1, 4),        # allow weekends/holidays gaps
    "monthly": (25, 40),
    "quarterly": (80, 100),
    "annual": (350, 380),
}


def validate_schema(records: list[dict], indicator_id: str) -> ValidationResult:
    result = ValidationResult(indicator_id=indicator_id)
    if not records:
        result.add_error("No records to validate (empty dataset).")
        return result
    columns = set(records[0].keys())
    missing = EXPECTED_COLUMNS - columns
    if missing:
        result.add_error(f"Missing expected columns: {missing}")
    return result


def validate_types(records: list[dict], indicator_id: str) -> ValidationResult:
    result = ValidationResult(indicator_id=indicator_id)
    for i, r in enumerate(records):
        try:
            datetime.fromisoformat(str(r.get("date")))
        except ValueError:
            result.add_error(f"Row {i}: unparseable date {r.get('date')!r}")
        if r.get("value") is not None:
            try:
                float(r["value"])
            except (TypeError, ValueError):
                result.add_error(f"Row {i}: non-numeric value {r.get('value')!r}")
    return result


def validate_missing_and_duplicates(records: list[dict], indicator_id: str) -> ValidationResult:
    result = ValidationResult(indicator_id=indicator_id)
    dates = [r.get("date") for r in records]
    seen = set()
    dupes = set()
    for d in dates:
        if d in seen:
            dupes.add(d)
        seen.add(d)
    if dupes:
        result.add_error(f"Duplicate dates found: {sorted(dupes)}")
    n_missing_values = sum(1 for r in records if r.get("value") in (None, ""))
    if n_missing_values:
        result.add_warning(f"{n_missing_values} rows with missing value.")
    return result


def validate_frequency(records: list[dict], indicator_id: str, expected_frequency: str) -> ValidationResult:
    result = ValidationResult(indicator_id=indicator_id)
    lo, hi = FREQUENCY_DELTA_DAYS.get(expected_frequency, (None, None))
    if lo is None or len(records) < 2:
        return result
    dates = sorted(datetime.fromisoformat(str(r["date"])) for r in records if r.get("date"))
    for a, b in zip(dates, dates[1:]):
        delta = (b - a).days
        if not (lo <= delta <= hi):
            result.add_warning(
                f"Gap of {delta} days between {a.date()} and {b.date()} "
                f"is outside expected range for frequency={expected_frequency} ({lo}-{hi}d)."
            )
    return result


def validate_no_impossible_values(records: list[dict], indicator_id: str, min_value: float | None = None,
                                   max_value: float | None = None) -> ValidationResult:
    result = ValidationResult(indicator_id=indicator_id)
    for r in records:
        v = r.get("value")
        if v is None:
            continue
        v = float(v)
        if min_value is not None and v < min_value:
            result.add_error(f"Value {v} below plausible minimum {min_value} on {r.get('date')}")
        if max_value is not None and v > max_value:
            result.add_error(f"Value {v} above plausible maximum {max_value} on {r.get('date')}")
    return result


def validate_outliers(records: list[dict], indicator_id: str, max_pct_jump: float = 0.5) -> ValidationResult:
    """Flags (warns, does not fail) period-over-period jumps larger than max_pct_jump."""
    result = ValidationResult(indicator_id=indicator_id)
    sorted_records = sorted(
        (r for r in records if r.get("value") is not None),
        key=lambda r: r["date"],
    )
    for prev, cur in zip(sorted_records, sorted_records[1:]):
        p, c = float(prev["value"]), float(cur["value"])
        if p == 0:
            continue
        pct = abs(c - p) / abs(p)
        if pct > max_pct_jump:
            result.add_warning(
                f"Unexpected jump of {pct:.1%} between {prev['date']} ({p}) and {cur['date']} ({c})."
            )
    return result


def check_structural_change(expected_columns: set[str], actual_columns: set[str], context: str) -> None:
    """Raise loudly with the WHAT CHANGED / EXPECTED / ACTUAL / ACTION REQUIRED format
    demanded by MASTER TASK section 6, if the source structure has drifted.
    """
    if expected_columns != actual_columns:
        raise StructuralChangeError(
            "\n".join([
                f"STRUCTURAL CHANGE DETECTED in {context}",
                f"WHAT CHANGED: source column set differs from what the pipeline expects",
                f"EXPECTED: {sorted(expected_columns)}",
                f"ACTUAL: {sorted(actual_columns)}",
                "ACTION REQUIRED: update the parser/config for this source, verify the new "
                "structure against the official site, then re-run. Do not patch around this silently.",
            ])
        )


def run_all(records: list[dict], indicator_id: str, expected_frequency: str,
            min_value: float | None = None, max_value: float | None = None) -> ValidationResult:
    combined = ValidationResult(indicator_id=indicator_id)
    for r in (
        validate_schema(records, indicator_id),
        validate_types(records, indicator_id),
        validate_missing_and_duplicates(records, indicator_id),
        validate_frequency(records, indicator_id, expected_frequency),
        validate_no_impossible_values(records, indicator_id, min_value, max_value),
        validate_outliers(records, indicator_id),
    ):
        combined.errors.extend(r.errors)
        combined.warnings.extend(r.warnings)
        combined.ok = combined.ok and r.ok
    return combined
