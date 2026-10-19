"""The three lagging groups fixed on 2026-09-26: bank soundness (IMF FSI continuing NBK
form 314), Minfin's quarterly general-government data, BNS monthly passenger turnover."""
import csv
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from fetchers import minfin  # noqa: E402
from lib import validation  # noqa: E402


def _processed(agency: str, indicator_id: str) -> dict[str, float]:
    with (REPO_ROOT / "data" / "processed" / agency / f"{indicator_id.lower()}.csv").open(encoding="utf-8") as f:
        return {r["date"]: float(r["value"]) for r in csv.DictReader(f)}


@pytest.mark.cross_source
@pytest.mark.parametrize("nbk_id,fsi_id", [("BANK_ROA", "FSI_ROA"), ("BANK_ROE", "FSI_ROE")])
def test_nbk_returns_equal_imf_fsi_once_dated_to_their_quarter(nbk_id, fsi_id):
    nbk, fsi = _processed("nbk", nbk_id), _processed("imf", fsi_id)
    common = sorted(set(nbk) & set(fsi))
    assert len(common) >= 16
    assert all(abs(nbk[d] - fsi[d]) < 0.01 for d in common)


@pytest.mark.cross_source
def test_nbk_capital_ratio_as_at_the_1st_equals_the_imf_quarter_end():
    """Point-in-time: NBK's 'на 01.04.2024' and IMF's 2024-03-31 are the same stock."""
    nbk, fsi = _processed("nbk", "CAPITAL_ADEQUACY_RATIO"), _processed("imf", "FSI_CAPITAL_ADEQUACY")
    pairs = [(d, f"{int(d[:4]) - (d[5:7] == '01'):04d}-{ {'01': '12-31', '04': '03-31', '07': '06-30', '10': '09-30'}[d[5:7]]}")
             for d in nbk]
    matched = [(a, b) for a, b in pairs if b in fsi]
    assert len(matched) >= 16
    assert all(abs(nbk[a] - fsi[b]) < 0.01 for a, b in matched)
    assert max(fsi) >= "2025-12-31"


@pytest.mark.cross_source
def test_imf_fsi_runs_past_the_nbk_stop():
    assert max(_processed("imf", "FSI_NPL_RATIO")) > max(_processed("nbk", "NPL_RATIO"))
    assert min(_processed("imf", "FSI_NPL_RATIO")) <= "2008-03-31"


def test_gg_coverage_year_follows_the_publication_calendar():
    assert minfin._gg_coverage_year({"created_date": "2026-03-05T10:00:00"}) == 2025   # Q4 in March
    assert minfin._gg_coverage_year({"created_date": "2026-09-17T10:00:00"}) == 2026
    assert minfin._gg_coverage_year({"created_date": "2020-06-01"}) == 2020


def test_gg_title_pattern_matches_every_wording_minfin_used():
    for title in ["General Government date 2023/3Q", "General Government Data Q1 2025",
                  "Data on the General Government sektor  (according to the IMF methodology) for the 2 Q of 2025",
                  "General government sector data for Q2 2026 (consolidated budget according to the IMF methodology)",
                  "Данные по сектору государственного управления (консолидированный бюджет по методологии МВФ) за 1 квартал 2026 года"]:
        assert minfin.GG_TITLE_RE.search(title), title
    assert not minfin.GG_TITLE_RE.search("Government Finance Statistics Data for 2024")


def test_gg_row_merges_editions_and_drops_mislabelled_and_zero_cells(monkeypatch):
    docs = [  # newest first, as the listing returns them
        {"id": 3, "created_date": "2021-08-10"},
        {"id": 2, "created_date": "2020-09-02"},   # Q2 2020 file headed "2019/1", "2019/2"
        {"id": 1, "created_date": "2020-06-01"},   # Q1 2020 file, future quarters pre-filled with 0
    ]
    cells = {1: [("2020-03-31", 10.0), ("2020-09-30", 0.0)],
             2: [("2019-03-31", 10.0), ("2019-06-30", 7.0)],
             3: [("2021-03-31", 12.0), ("2021-06-30", 13.0)]}
    monkeypatch.setattr(minfin, "_find_gg_documents", lambda: docs)
    monkeypatch.setattr(minfin, "_fetch_gg_row_from", lambda doc, row, iid: (
        [{"date": d, "value": v} for d, v in cells[doc["id"]]], {"frequency": "quarterly"}))
    records, manifest = minfin._fetch_gg_row(11, "GG_TAXES")
    assert [r["date"] for r in records] == ["2020-03-31", "2021-03-31", "2021-06-30"]
    assert len(manifest["cells_dropped"]) == 3


def test_gg_row_raises_when_the_newest_edition_does_not_parse(monkeypatch):
    docs = [{"id": 2, "created_date": "2026-09-17"}, {"id": 1, "created_date": "2026-06-05"}]
    monkeypatch.setattr(minfin, "_find_gg_documents", lambda: docs)

    def fake(doc, row, iid):
        if doc["id"] == 2:
            raise validation.StructuralChangeError("x\nWHAT CHANGED: layout")
        return [{"date": "2026-03-31", "value": 1.0}], {}
    monkeypatch.setattr(minfin, "_fetch_gg_row_from", fake)
    with pytest.raises(validation.StructuralChangeError):
        minfin._fetch_gg_row(11, "GG_TAXES")


def test_gg_quarterly_history_reaches_back_before_2025_and_forward_to_2026():
    taxes = _processed("minfin", "GG_TAXES")
    assert min(taxes) <= "2021-01-01" and max(taxes) >= "2026-04-01"


def test_passenger_turnover_monthly_has_the_taldau_history():
    ytd = _processed("bns", "PASSENGER_TURNOVER_MONTHLY")
    assert min(ytd) <= "2021-01-01"
    # year-to-date: December is the year; 2021 and 2023 sit either side of the second break
    assert 100_000 < ytd["2021-12-01"] < 115_000 and 65_000 < ytd["2023-12-01"] < 80_000


def test_one_failed_dataset_does_not_block_the_run():
    import update_all
    from lib.pipeline_logging import LogEntry
    ok = [LogEntry(timestamp="t", source="bns", dataset=f"S{i}", action="fetch", status="ok") for i in range(99)]
    bad = LogEntry(timestamp="t", source="imf", dataset="FSI_ROA", action="fetch", status="error", errors=["reset"])
    proceed, failed = update_all.failure_gate(ok + [bad])
    assert proceed and failed == [bad]
    outage = [LogEntry(timestamp="t", source="imf", dataset=f"X{i}", action="fetch", status="error") for i in range(30)]
    assert not update_all.failure_gate(ok[:70] + outage)[0]


def test_a_failed_cross_source_check_is_reported_not_blocking(monkeypatch, tmp_path):
    """Tests marked cross_source run apart from the blocking ones: their failures come back
    as a list for the warnings and the report, and the blocking run never selects them."""
    import subprocess
    import update_all
    from lib.pipeline_logging import RunLogger
    line = "tests/test_imf_dims.py::test_imf_net_iip_is_nbks_one_day_earlier - AssertionError: x"
    selections = []

    def fake_run(cmd, **kwargs):
        selections.append(cmd[-1])
        if cmd[-1] == "cross_source":
            return subprocess.CompletedProcess(cmd, 1, f"F.\nFAILED {line}\n1 failed, 1 passed\n", "")
        return subprocess.CompletedProcess(cmd, 0, "814 passed\n", "")

    monkeypatch.setattr(update_all.subprocess, "run", fake_run)
    blocking, _, failed = update_all.run_tests()
    assert selections == ["not cross_source", "cross_source"]
    assert blocking.returncode == 0 and failed == [line]
    # A cross-source run that dies without a FAILED line is still reported.
    monkeypatch.setattr(update_all.subprocess, "run",
                        lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0 if cmd[-1] != "cross_source" else 2,
                                                                      "", "ImportError: boom"))
    assert update_all.run_tests()[2] == ["cross-source run exited 2: ImportError: boom"]
    monkeypatch.setattr(update_all, "REPO_ROOT", tmp_path)
    update_all._write_report("t", RunLogger(run_timestamp="t"), unified_updated=True, tests_passed=True,
                             cross_source_failed=[line])
    report = next((tmp_path / "reports").glob("update_report_*.md")).read_text(encoding="utf-8")
    assert "Cross-source checks failed: 1" in report and line in report


def test_the_comparisons_between_publications_are_marked_cross_source():
    from tests import test_date_basis, test_imf_dims
    for fn in (test_date_basis.test_quarterly_current_account_sums_to_the_imf_calendar_year,
               test_imf_dims.test_imf_net_iip_is_nbks_one_day_earlier,
               test_nbk_returns_equal_imf_fsi_once_dated_to_their_quarter):
        assert "cross_source" in {m.name for m in getattr(fn, "pytestmark", [])}, fn.__name__
