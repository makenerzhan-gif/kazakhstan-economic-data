import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from lib import revisions


def test_detect_revisions_finds_changed_value():
    old = [{"date": "2026-01-01", "value": 100.0}]
    new = [{"date": "2026-01-01", "value": 105.0}]
    revs = revisions.detect_revisions("GDP_REAL", "bns", old, new, date(2026, 8, 30))
    assert len(revs) == 1
    assert revs[0].old_value == 100.0
    assert revs[0].new_value == 105.0


def test_detect_revisions_ignores_unchanged():
    old = [{"date": "2026-01-01", "value": 100.0}]
    new = [{"date": "2026-01-01", "value": 100.0}]
    revs = revisions.detect_revisions("GDP_REAL", "bns", old, new, date(2026, 8, 30))
    assert revs == []


def test_detect_revisions_ignores_new_period():
    old = [{"date": "2026-01-01", "value": 100.0}]
    new = [{"date": "2026-01-01", "value": 100.0}, {"date": "2026-02-01", "value": 110.0}]
    revs = revisions.detect_revisions("GDP_REAL", "bns", old, new, date(2026, 8, 30))
    assert revs == []
