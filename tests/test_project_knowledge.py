"""project_knowledge/ is synced into a Claude Project with a limited context: it must stay
small, and its latest snapshot must be one row per series."""
import csv
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PK = REPO_ROOT / "project_knowledge"
BUDGET_BYTES = 600_000  # ~0.4 MB today; the old wide copy alone was 5.5 MB

sys.path.insert(0, str(REPO_ROOT / "scripts"))
import build_project_knowledge as bpk  # noqa: E402


def test_project_knowledge_fits_its_budget():
    size = sum(p.stat().st_size for p in PK.rglob("*") if p.is_file())
    assert size < BUDGET_BYTES, f"project_knowledge/ is {size:,} bytes"


def test_latest_snapshot_is_one_row_per_series_with_the_last_values():
    path = PK / "latest" / "macro_latest.csv"
    with path.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    ids = [r["id"] for r in rows]
    assert len(ids) == len(set(ids)) and len(ids) >= 400
    cpi = next(r for r in rows if r["id"] == "CPI")
    assert cpi["last_date"] > cpi["prev_date"] and float(cpi["last_value"]) > 0 and cpi["name_ru"]


def test_short_keeps_the_first_sentence_and_escapes_pipes():
    assert bpk._short("One. Two.") == "One."
    assert bpk._short("a | b") == "a / b"
    assert len(bpk._short("x" * 500)) == 180
