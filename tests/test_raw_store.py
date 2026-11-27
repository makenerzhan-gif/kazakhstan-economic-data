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


def _lfs_pointer(content: bytes) -> bytes:
    """What actions/checkout leaves in place of an LFS-tracked file when lfs is off."""
    import hashlib
    return (b"version https://git-lfs.github.com/spec/v1\n"
            b"oid sha256:" + hashlib.sha256(content).hexdigest().encode() + b"\n"
            b"size " + str(len(content)).encode() + b"\n")


def test_an_lfs_pointer_to_the_same_bytes_counts_as_the_archived_copy(isolated_raw_root):
    """Regression test for the CI duplicates of 2026-09-16..23: the workflow checks the
    repository out without LFS content, so every archived BNS workbook is a 130-byte
    pointer there. Comparing bytes saw a 'different' file every day and archived the
    unchanged workbook again (58 copies a day). The pointer names the sha256 of the
    content it stands for, and that is what must be compared."""
    folder = isolated_raw_root / "bns"
    folder.mkdir()
    (folder / "bns_exports_2026-09-22.xlsx").write_bytes(_lfs_pointer(b"same bytes"))
    same_day = folder / "bns_exports_2026-09-23.xlsx"
    same_day.write_bytes(_lfs_pointer(b"same bytes"))

    assert raw_store.save_raw_bytes("bns", "EXPORTS", date(2026, 9, 23), "xlsx", b"same bytes") == same_day
    assert raw_store.save_raw_bytes("bns", "OIL_EXPORTS_VALUE", date(2026, 9, 24), "xlsx", b"same bytes") == folder / "bns_exports_2026-09-22.xlsx"
    assert sorted(p.name for p in folder.iterdir()) == ["bns_exports_2026-09-22.xlsx", "bns_exports_2026-09-23.xlsx"]

    revised = raw_store.save_raw_bytes("bns", "EXPORTS", date(2026, 9, 23), "xlsx", b"revised bytes")   # a real revision still lands
    assert revised.name.startswith("bns_exports_2026-09-23_") and revised.read_bytes() == b"revised bytes"
    assert same_day.read_bytes() == _lfs_pointer(b"same bytes"), "the pointer is never touched"


def test_lfs_pointer_oid_reads_only_real_pointers():
    assert raw_store.lfs_pointer_oid(_lfs_pointer(b"x")) == "2d711642b726b04401627ca9fbac32f5c8530fb1903cc4db02258717921a4881"
    assert raw_store.lfs_pointer_oid(b"version 1\noid sha256:abc\n") is None
    assert raw_store.lfs_pointer_oid(b"PK\x03\x04 a real workbook") is None
    assert raw_store.lfs_pointer_oid(b"") is None


def test_latest_raw_file_is_never_a_manifest(isolated_raw_root):
    """`x_2026-09-25.manifest.json` sorts after `x_2026-09-25.json`; it was returned until
    2026-09-26 and every unchanged WITS answer was compared with it, and archived again."""
    path = raw_store.save_raw_bytes("wits", "EXPORTS", date(2026, 9, 25), "json", b"{}")
    raw_store.write_download_manifest("wits", "EXPORTS", date(2026, 9, 25), {"raw_file": path.name})
    assert raw_store.latest_raw_file("wits", "EXPORTS") == path


def test_an_unchanged_answer_keeps_two_manifests_not_one_per_run(isolated_raw_root):
    """First seen and latest download; the 57 619 manifests of 2026-11-27 were one per indicator per run."""
    info = lambda day: {"downloaded_at": f"{day}T06:00:00", "source_url": "https://x", "raw_file": "a.json"}   # noqa: E731
    for day in (1, 2, 3, 4):
        raw_store.write_download_manifest("bns", "CPI", date(2026, 11, day), info(f"2026-11-0{day}"))
    names = [p.name for p in raw_store.indicator_manifests("bns", "CPI")]
    assert names == ["bns_cpi_2026-11-01.manifest.json", "bns_cpi_2026-11-04.manifest.json"]
    # a changed answer starts a new pair; the old pair stays
    raw_store.write_download_manifest("bns", "CPI", date(2026, 11, 5), {**info("2026-11-05"), "raw_file": "b.json"})
    raw_store.write_download_manifest("bns", "CPI", date(2026, 11, 6), {**info("2026-11-06"), "raw_file": "b.json"})
    raw_store.write_download_manifest("bns", "CPI", date(2026, 11, 7), {**info("2026-11-07"), "raw_file": "b.json"})
    assert [p.name[8:18] for p in raw_store.indicator_manifests("bns", "CPI")] == ["2026-11-01", "2026-11-04", "2026-11-05", "2026-11-07"]
    # the manifests of an indicator whose id starts the same are not touched or counted
    raw_store.write_download_manifest("bns", "CPI_YOY", date(2026, 11, 7), info("2026-11-07"))
    assert len(raw_store.indicator_manifests("bns", "CPI")) == 4


def test_collapse_manifests_keeps_the_ends_of_every_run_of_identical_answers(isolated_raw_root):
    import json
    folder = isolated_raw_root / "nbk"
    folder.mkdir()
    bodies = ["a", "a", "a", "a", "b", "a", "a"]
    for i, b in enumerate(bodies, start=1):
        (folder / f"nbk_m2_2026-10-{i:02d}.manifest.json").write_text(json.dumps({"downloaded_at": str(i), "raw_file": b}))
    assert len(raw_store.collapse_manifests("nbk", "M2", dry_run=True)) == 2
    removed = raw_store.collapse_manifests("nbk", "M2")
    assert [p.name[7:17] for p in removed] == ["2026-10-02", "2026-10-03"]
    assert len(raw_store.indicator_manifests("nbk", "M2")) == 5
