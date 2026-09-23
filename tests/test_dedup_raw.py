"""scripts/dedup_raw.py: one raw file per distinct content, every manifest that named a
removed copy re-pointed at the survivor -- including the manifests of OTHER indicators
that read the same shared file, and manifests an earlier dedup left dangling."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import dedup_raw  # noqa: E402


def _manifest(folder: Path, name: str, raw_file: str) -> Path:
    p = folder / f"{name}.manifest.json"
    p.write_text(json.dumps({"downloaded_at": "2026-09-16T06:00:00", "raw_file": raw_file}), encoding="utf-8")
    return p


@pytest.fixture
def raw(tmp_path, monkeypatch):
    monkeypatch.setattr(dedup_raw, "RAW", tmp_path)
    monkeypatch.setattr(dedup_raw, "REPO_ROOT", tmp_path.parent)
    bns = tmp_path / "bns"
    bns.mkdir()
    return bns


def test_shared_file_manifests_of_every_indicator_are_repointed(raw):
    (raw / "bns_avg_wage_quarterly_346883_2026-09-15.xlsx").write_bytes(b"wage table")
    (raw / "bns_avg_wage_quarterly_346883_2026-09-16.xlsx").write_bytes(b"wage table")        # CI re-archived it
    (raw / "bns_imports_2026-09-16.xlsx").write_bytes(b"something else")
    own = _manifest(raw, "bns_avg_wage_quarterly_346883_2026-09-16", "bns_avg_wage_quarterly_346883_2026-09-16.xlsx")
    shared = _manifest(raw, "bns_avg_wage_agriculture_346883_2026-09-16", "bns_avg_wage_quarterly_346883_2026-09-16.xlsx")
    other = _manifest(raw, "bns_imports_2026-09-16", "bns_imports_2026-09-16.xlsx")

    assert dedup_raw.main([]) == 0
    assert sorted(p.name for p in raw.glob("*.xlsx")) == ["bns_avg_wage_quarterly_346883_2026-09-15.xlsx", "bns_imports_2026-09-16.xlsx"]
    for m in (own, shared):
        info = json.loads(m.read_text(encoding="utf-8"))
        assert info["raw_file"] == "bns_avg_wage_quarterly_346883_2026-09-15.xlsx", m.name
        assert "removed" in info["raw_file_note"]
    assert json.loads(other.read_text(encoding="utf-8")) == {"downloaded_at": "2026-09-16T06:00:00", "raw_file": "bns_imports_2026-09-16.xlsx"}
    record = json.loads(next(raw.parent.glob("dedup_*.json")).read_text(encoding="utf-8"))
    rel = raw.parent.name + "/bns/"                                    # paths are relative to REPO_ROOT (= data/raw's parent here)
    assert record["removed"] == {rel + "bns_avg_wage_quarterly_346883_2026-09-16.xlsx": rel + "bns_avg_wage_quarterly_346883_2026-09-15.xlsx"}
    assert record["removed_files"] == 1


def test_repair_follows_dedup_records_across_chains_and_leaves_unknown_files_alone(raw, capsys):
    (raw / "bns_cpi_2026-09-01.xlsx").write_bytes(b"cpi")
    (raw.parent / "dedup_2026-09-15.json").write_text(json.dumps({"removed": {
        "data/raw/bns/bns_cpi_2026-09-10.xlsx": "data/raw/bns/bns_cpi_2026-09-05.xlsx"}}), encoding="utf-8")
    (raw.parent / "dedup_2026-09-23.json").write_text(json.dumps({"removed": {
        "data/raw/bns/bns_cpi_2026-09-05.xlsx": "data/raw/bns/bns_cpi_2026-09-01.xlsx"}}), encoding="utf-8")
    chained = _manifest(raw, "bns_cpi_2026-09-10", "bns_cpi_2026-09-10.xlsx")            # 09-10 -> 09-05 -> 09-01
    direct = _manifest(raw, "bns_cpi_2026-09-05", "bns_cpi_2026-09-05.xlsx")
    unknown = _manifest(raw, "bns_gdp_2026-09-05", "bns_gdp_2026-09-05.xlsx")             # missing, no record
    fine = _manifest(raw, "bns_cpi_2026-09-01", "bns_cpi_2026-09-01.xlsx")

    assert dedup_raw.repair_manifests("2026-09-23", dry_run=True) == 2
    assert json.loads(chained.read_text(encoding="utf-8"))["raw_file"] == "bns_cpi_2026-09-10.xlsx"   # dry run changes nothing
    assert dedup_raw.repair_manifests("2026-09-23") == 2
    for m in (chained, direct):
        assert json.loads(m.read_text(encoding="utf-8"))["raw_file"] == "bns_cpi_2026-09-01.xlsx", m.name
    assert json.loads(unknown.read_text(encoding="utf-8"))["raw_file"] == "bns_gdp_2026-09-05.xlsx"
    assert "raw_file_note" not in json.loads(fine.read_text(encoding="utf-8"))
    assert "bns_gdp_2026-09-05.xlsx" in capsys.readouterr().out
