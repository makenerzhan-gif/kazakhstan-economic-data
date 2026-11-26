"""ARDFM banking bulletin series dated by `date_basis: next_period_start`: the fetcher merges its stored
history, so a second run must not shift it again (until 2026-11-26 every run added a month at the front --
BANK_NET_INCOME grew from 6 to 66 rows of the same value, and each month after April carried the next one's)."""
import csv
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
from fetchers import ardfm  # noqa: E402
from lib import periods  # noqa: E402

EDITIONS = {"05": 795.9, "06": 1035.7, "07": 1195.6, "08": 1396.5}


def _run(tmp_path, monkeypatch):
    docs = [{"id": i, "title": f"Текущее состояние банковского сектора РК по состоянию на 01.{m}.2026",
             "full_text": [{"document": f"/{m}.pdf"}]} for i, m in enumerate(EDITIONS)]
    monkeypatch.setattr(ardfm, "PROCESSED_ROOT", tmp_path)
    monkeypatch.setattr(ardfm, "_list_banking_bulletins", lambda ind: docs)
    monkeypatch.setattr(ardfm, "_download", lambda path: path.encode())
    monkeypatch.setattr(ardfm, "_pdf_text", lambda content: content.decode())
    monkeypatch.setattr(ardfm, "_table_body", lambda text, n: text)
    monkeypatch.setattr(ardfm, "_row_numbers", lambda table, label, ind, expect, exclude=None: [2723.7, EDITIONS[table[1:3]]])
    monkeypatch.setattr(ardfm, "_column_dates", lambda table, ind: [(2026, 1), (2026, int(table[1:3]))])
    monkeypatch.setattr(ardfm, "_save_raw", lambda *a, **k: None)
    records, _ = ardfm.fetch_bank_net_income()
    records = periods.apply_date_basis(records, "monthly", ardfm._date_basis("BANK_NET_INCOME"))   # as update_ardfm.py does
    out = sorted((r["date"], r["value"]) for r in records)
    with (tmp_path / "bank_net_income.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "value"])
        w.writerows(out)
    return out


def test_the_stored_history_is_not_shifted_again(tmp_path, monkeypatch):
    first = _run(tmp_path, monkeypatch)
    assert first == [("2026-04-01", 795.9), ("2026-05-01", 1035.7), ("2026-06-01", 1195.6), ("2026-07-01", 1396.5)]
    assert _run(tmp_path, monkeypatch) == first and _run(tmp_path, monkeypatch) == first


def test_shift_forward_undoes_shift_back():
    for d, f in (("2026-01-01", "monthly"), ("2026-12-01", "monthly"), ("2026-01-01", "quarterly"), ("2026-10-01", "quarterly")):
        assert periods.shift_back_one_period(periods.shift_forward_one_period(d, f), f) == d


@pytest.mark.parametrize("name", ["bank_net_income", "bank_roa_monthly", "bank_roe_monthly", "bank_liquid_assets"])
def test_no_run_of_copied_values_at_the_front(name):
    path = REPO / "data" / "processed" / "ardfm" / f"{name}.csv"
    if not path.exists():
        pytest.skip("processed file absent")
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    assert rows[0]["date"] >= "2026-04-01", rows[0]                 # the first bulletin read is the one as of 01.05.2026
