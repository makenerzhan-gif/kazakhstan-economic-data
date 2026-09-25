"""Source dates restated to the period an observation covers (audit 2026-09-25).

NBK open data stamps a flow or an average with the day AFTER its period: the
balance of payments for Q1 2020 arrives as report_date 2020-04-01. The values
were right and every lag built on them was one period off. `date_basis` in
indicators.yaml marks those series; `periods.apply_date_basis` moves them back.
Separately, `processed_store.write_processed` used to restate point-in-time
stocks to the period start, so the National Fund's end-of-June portfolio landed
on 1 April."""
import csv
import sys
from collections import defaultdict
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from lib import periods, processed_store  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
INDICATORS = yaml.safe_load((REPO_ROOT / "config" / "indicators.yaml").read_text(encoding="utf-8"))["indicators"]


def _processed(agency: str, indicator_id: str) -> dict[str, float]:
    path = REPO_ROOT / "data" / "processed" / agency / f"{indicator_id.lower()}.csv"
    with path.open(encoding="utf-8") as f:
        return {r["date"]: float(r["value"]) for r in csv.DictReader(f)}


def test_shift_back_one_period_crosses_year_boundaries():
    assert periods.shift_back_one_period("2020-04-01", "quarterly") == "2020-01-01"
    assert periods.shift_back_one_period("2021-01-01", "quarterly") == "2020-10-01"
    assert periods.shift_back_one_period("2021-02-15", "quarterly") == "2020-10-01"
    assert periods.shift_back_one_period("2026-08-01", "monthly") == "2026-07-01"
    assert periods.shift_back_one_period("2026-01-01", "monthly") == "2025-12-01"
    assert periods.shift_back_one_period("2026-01-01", "annual") == "2026-01-01"


def test_apply_date_basis_only_moves_marked_series():
    recs = [{"date": "2026-04-01", "value": 1.0}]
    assert periods.apply_date_basis(recs, "quarterly", None) == recs
    assert periods.apply_date_basis(recs, "quarterly", periods.NEXT_PERIOD_START) == [{"date": "2026-01-01", "value": 1.0}]


def test_every_date_basis_is_evidenced_and_applies_to_flows_only():
    marked = [i for i in INDICATORS if "date_basis" in i]
    assert len(marked) >= 30
    for i in marked:
        assert i["date_basis"] == periods.NEXT_PERIOD_START, i["id"]
        assert i.get("date_basis_evidence"), i["id"]
        assert i["frequency"] in periods.NORMALISED_FREQUENCIES, i["id"]
        # A stock "as at 1 July" is a correct point-in-time date; only flows and
        # averages have a covered period to move to.
        assert i.get("observation_type") != "point_in_time", i["id"]


def test_quarterly_current_account_sums_to_the_imf_calendar_year():
    """The proof the shift is right: four quarters of a calendar year add up to the
    IMF's annual figure only after the relabelling (2020: -11 054.8 mln USD)."""
    quarters = _processed("nbk", "CURRENT_ACCOUNT_BALANCE")
    imf = {d[:4]: v / 1e6 for d, v in _processed("imf", "IMF_CURRENT_ACCOUNT_USD").items()}
    by_year = defaultdict(list)
    for d, v in quarters.items():
        by_year[d[:4]].append(v)
    checked = 0
    for year in ("2020", "2021", "2022", "2023", "2024"):
        assert len(by_year[year]) == 4, year
        assert abs(sum(by_year[year]) - imf[year]) < 1.0, (year, sum(by_year[year]), imf[year])
        checked += 1
    assert checked == 5


def test_year_to_date_pension_payments_restart_in_january():
    """With the source's next-month dating, the 1 January point held the whole
    previous year and decumulation produced a negative February."""
    series = sorted(_processed("nbk", "PENSION_PAYMENTS").items())
    for (d0, v0), (d1, v1) in zip(series, series[1:]):
        if d0[:4] == d1[:4]:
            assert v1 >= v0, (d0, v0, d1, v1)


def test_write_processed_keeps_a_point_in_time_stock_on_its_own_date(tmp_path, monkeypatch):
    monkeypatch.setattr(processed_store, "PROCESSED_ROOT", tmp_path)
    path = processed_store.write_processed(
        "minfin", "NATIONAL_FUND_GOLD", [{"date": "2026-06-30", "value": 1.0}], frequency="quarterly")
    assert path.read_text(encoding="utf-8").splitlines()[1].startswith("2026-06-30,")
    # A period-labelled series is still restated to the period start.
    path = processed_store.write_processed(
        "nbk", "CURRENT_ACCOUNT_BALANCE", [{"date": "2026-03-31", "value": 1.0}], frequency="quarterly")
    assert path.read_text(encoding="utf-8").splitlines()[1].startswith("2026-01-01,")


def test_year_to_date_series_say_so_in_the_transformation_column():
    for i in INDICATORS:
        if i.get("cumulation") != "year_to_date":
            continue
        path = REPO_ROOT / "data" / "processed" / i["agency"] / f"{i['id'].lower()}.csv"
        with path.open(encoding="utf-8") as f:
            labels = {r["transformation"] for r in csv.DictReader(f)}
        assert labels and all("year-to-date" in t for t in labels), (i["id"], labels)


def test_every_known_source_issue_names_a_real_series_and_pins_real_values():
    """config/source_issues.yaml lists what the official files get wrong; each entry must
    point at a series the pipeline carries, and when it pins values they must parse."""
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import build_project_knowledge as bpk
    dims_ids = {d["id"] for d in yaml.safe_load((REPO_ROOT / "config" / "dims.yaml").read_text(encoding="utf-8"))["datasets"]}
    known = {i["id"] for i in INDICATORS} | dims_ids
    issues = bpk.load_source_issues()
    assert issues
    for issue in issues:
        assert issue["kind"] in {"error", "break", "inconsistent", "preliminary", "caveat"}, issue["id"]
        assert issue["variable"] in known and all(v in known for v in issue.get("also", [])), issue["id"]
        assert issue.get("advice") and issue.get("evidence"), issue["id"]
        for obs in issue.get("observations") or []:
            float(obs["value"])
        assert bpk.issue_status(issue) in ("still in the data", "caveat") or "corrected" in bpk.issue_status(issue)
