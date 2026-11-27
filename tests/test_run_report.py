"""lib/run_report: new warnings against the previous run, and the revisions summary."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from lib import run_report as rr  # noqa: E402

JUMP = "Unexpected jump of 40% in value between 2026-09-01 (1.0) and 2026-10-01 (1.4)."
OLD = "Gap of 62 days between 2019-01-01 and 2019-03-04 is outside expected range for frequency=monthly (28-31d)."
SKIP = "not re-downloaded: last download 2026-11-20, refreshed every 7 days"


def _entries():
    return [SimpleNamespace(source="bns", dataset="CPI", warnings=[JUMP, OLD, SKIP]),
            SimpleNamespace(source="nbk", dataset="M2", warnings=[])]


def test_only_warnings_the_previous_run_did_not_raise_are_new():
    new, seen, kinds = rr.split_warnings(_entries(), {rr.key("bns", "CPI", OLD)})
    assert new == {0: [JUMP]}
    assert kinds == {"jump": 1, "gap": 1, "not re-downloaded": 1}
    assert seen == {rr.key("bns", "CPI", OLD), rr.key("bns", "CPI", JUMP)}      # the volatile kind is never stored
    text = "\n".join(rr.warning_lines(_entries(), new, kinds, baseline=False))
    assert "3 in all" in text and "### New this run: 1 in 1 datasets" in text and JUMP in text and OLD not in text


def test_the_first_run_is_the_baseline(tmp_path):
    assert rr.load_known(tmp_path / "none.txt") is None
    new, seen, kinds = rr.split_warnings(_entries(), None)
    assert new == {}
    assert "this run is the baseline" in "\n".join(rr.warning_lines(_entries(), new, kinds, baseline=True))
    rr.save_known(seen, tmp_path / "k.txt")
    assert rr.load_known(tmp_path / "k.txt") == seen
    assert rr.split_warnings(_entries(), seen)[0] == {}


def test_the_same_text_in_another_dataset_is_another_warning():
    assert rr.key("bns", "CPI", JUMP) != rr.key("bns", "PPI", JUMP)
    assert rr.latest_date(JUMP) == "2026-10-01" and rr.latest_date("no date") == ""


def test_revisions_summary_separates_routine_revisers(tmp_path):
    def write(name, rows):
        (tmp_path / f"{name.lower()}_revisions.jsonl").write_text(
            "".join(json.dumps({"indicator_id": name, "period": p, "old_value": o, "new_value": n, "detected_date": d,
                                "source": "s", "reason": "r"}) + "\n" for p, o, n, d in rows), encoding="utf-8")
    write("GDP_SA", [("2026-01-01", 100, 101, f"2026-11-{d:02d}") for d in range(1, 8)] + [("2026-04-01 A @AKM", 100, 102, "2026-11-27")])
    write("NON_OIL", [("2021-12-31", 2.0, -8.0, "2026-11-27"), ("2020-12-31", 0, 5.0, "2026-11-27")])
    write("QUIET", [("2021-12-31", 1.0, 2.0, "2026-11-01")])
    rows = {r["id"]: r for r in rr.revisions_of("2026-11-27", tmp_path)}
    assert set(rows) == {"GDP_SA", "NON_OIL"}
    assert rows["GDP_SA"]["earlier_runs"] == 7 and rows["GDP_SA"]["first"] == "2026-04-01"
    assert rows["NON_OIL"]["n"] == 2 and rows["NON_OIL"]["max_pct"] == 500.0 and rows["NON_OIL"]["earlier_runs"] == 0
    text = "\n".join(rr.revision_lines(list(rows.values())))
    assert "- **NON_OIL**: 2 observations, 2020-12-31..2021-12-31, largest change 500%" in text
    assert "### Revised routinely: 1" in text and "GDP_SA (1)" in text
    assert rr.revision_lines([])[2] == "None this run."
