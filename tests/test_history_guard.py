"""lib/history_guard: what a run did to the history that was already stored."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from lib import history_guard as g  # noqa: E402

HEAD = "date,value,transformation\n"


def _csv(rows):
    return HEAD + "".join(f"{d},{v},level\n" for d, v in rows)


def test_new_points_at_the_end_are_not_a_finding():
    old = _csv([("2026-01-01", 1), ("2026-02-01", 2)])
    assert g.compare(old, old + "2026-03-01,3,level\n") == []


def test_the_ardfm_shift_is_found_twice():
    """Rows shifted a month back on every run: the start moves and one value repeats."""
    old = _csv([(f"2026-{m:02d}-01", 795.9) for m in range(3, 6)] + [("2026-06-01", 800.1), ("2026-07-01", 801.0)])
    new = _csv([(f"2025-{m:02d}-01", 795.9) for m in range(9, 13)] + [(f"2026-{m:02d}-01", 795.9) for m in range(1, 6)]
               + [("2026-06-01", 800.1), ("2026-07-01", 801.0)])
    found = g.compare(old, new)
    assert any(f.startswith("start moved back from 2026-03-01 to 2025-09-01 (6 observations") for f in found)
    assert any(f.startswith("9 identical values in a row") and "before was 3" in f for f in found)


def test_inserted_and_removed_observations():
    old = _csv([("2026-01-01", 1), ("2026-03-01", 3), ("2026-04-01", 4)])
    new = _csv([("2026-01-01", 1), ("2026-02-01", 2), ("2026-04-01", 4), ("2026-05-01", 5)])
    assert g.compare(old, new) == ["1 observations inserted inside the stored span (2026-02-01..2026-02-01)",
                                   "1 stored observations removed (2026-03-01..2026-03-01)"]


def test_a_step_function_that_only_grows_at_the_end_is_not_flat_news():
    old = _csv([(f"2026-01-{d:02d}", 16.5) for d in range(1, 21)])
    new = _csv([(f"2026-01-{d:02d}", 16.5) for d in range(1, 29)])
    assert g.compare(old, new) == []


def test_item_level_files_report_start_and_removals_only():
    head = "date,region,item_code,item_name,value,transformation\n"
    old = head + "2026-01-01,national,A,a,1,level\n2026-02-01,national,A,a,2,level\n"
    new = head + "2025-12-01,national,A,a,0,level\n2026-01-01,national,A,a,1,level\n2026-01-01,national,B,b,1,level\n"
    assert g.compare(old, new) == ["start moved back from 2026-01-01 to 2025-12-01 (1 observations before the old start)",
                                   "1 stored observations removed (2026-02-01..2026-02-01)"]


def test_report_lines_and_no_git_is_no_finding(tmp_path, monkeypatch):
    assert g.report_lines([]) == []
    lines = g.report_lines([{"file": "ardfm/x.csv", "finding": "start moved back"}])
    assert lines[0] == "## Stored history changed shape" and "- **ardfm/x.csv**: start moved back" in lines
    monkeypatch.setattr(g, "REPO_ROOT", tmp_path)          # not a repository
    assert g.findings() == []
