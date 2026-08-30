import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from lib import raw_store


@pytest.fixture
def isolated_raw_root(tmp_path, monkeypatch):
    """Point raw_store at a throwaway directory so these tests never touch the
    real data/raw/ tree."""
    monkeypatch.setattr(raw_store, "RAW_ROOT", tmp_path)
    return tmp_path


def test_first_save_writes_plain_dated_file(isolated_raw_root):
    path = raw_store.save_raw_bytes("bns", "CPI", date(2026, 8, 30), "csv", b"version-a")
    assert path.name == "bns_cpi_2026-08-30.csv"
    assert path.read_bytes() == b"version-a"


def test_identical_same_day_resave_is_a_noop(isolated_raw_root):
    first = raw_store.save_raw_bytes("bns", "CPI", date(2026, 8, 30), "csv", b"version-a")
    second = raw_store.save_raw_bytes("bns", "CPI", date(2026, 8, 30), "csv", b"version-a")
    assert first == second
    assert list(isolated_raw_root.glob("*/bns_cpi_*")) == [first]


def test_differing_same_day_resave_archives_a_new_version_without_touching_the_original(isolated_raw_root):
    """Regression test for the 2026-08-30 CI failure: a same-day re-fetch that came
    back with different bytes (source republished intraday) used to raise
    FileExistsError and halt the whole pipeline run. It must now archive the new
    content separately and leave the original file completely untouched.
    """
    original_path = raw_store.save_raw_bytes("bns", "CPI", date(2026, 8, 30), "csv", b"version-a")
    new_path = raw_store.save_raw_bytes("bns", "CPI", date(2026, 8, 30), "csv", b"version-b")

    assert new_path != original_path
    assert original_path.exists()
    assert original_path.read_bytes() == b"version-a", "original file must never be modified"
    assert new_path.read_bytes() == b"version-b"
    assert new_path.name.startswith("bns_cpi_2026-08-30_")


def test_latest_raw_file_returns_the_newest_version_after_a_same_day_revision(isolated_raw_root):
    raw_store.save_raw_bytes("bns", "CPI", date(2026, 8, 30), "csv", b"version-a")
    newest = raw_store.save_raw_bytes("bns", "CPI", date(2026, 8, 30), "csv", b"version-b")
    assert raw_store.latest_raw_file("bns", "CPI") == newest


def test_three_distinct_same_day_versions_are_all_preserved(isolated_raw_root):
    """Not just two -- an arbitrary number of intraday revisions must all survive."""
    p1 = raw_store.save_raw_bytes("bns", "CPI", date(2026, 8, 30), "csv", b"version-a")
    p2 = raw_store.save_raw_bytes("bns", "CPI", date(2026, 8, 30), "csv", b"version-b")
    p3 = raw_store.save_raw_bytes("bns", "CPI", date(2026, 8, 30), "csv", b"version-c")
    assert len({p1, p2, p3}) == 3
    for p, content in ((p1, b"version-a"), (p2, b"version-b"), (p3, b"version-c")):
        assert p.read_bytes() == content
