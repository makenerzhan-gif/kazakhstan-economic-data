import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import update_nbk


def test_fetchers_registered_for_every_indicator():
    """See tests/test_bns.py for why this doesn't call the fetchers themselves."""
    assert set(update_nbk.FETCHERS.keys()) == set(update_nbk.INDICATOR_IDS)
    for indicator_id, fn in update_nbk.FETCHERS.items():
        assert callable(fn), f"{indicator_id}'s fetcher is not callable"


def _bop_row(date, code, amount, form_type="USD mln", **extra):
    base = {"report_date": date, "amount": amount, "type": form_type, "period": "quarter",
            "account_type_code": "Current account", "code": code}
    return {**base, **extra}


def _bop_quarter(date, goods, services=-1.0, primary=-2.0, secondary=0.5, form_type="USD mln"):
    return [
        _bop_row(date, "Goods", goods, form_type, instrument_type_code="Goods and services", instrument_subtype1_code="Goods"),
        _bop_row(date, "Services", services, form_type, instrument_type_code="Goods and services", instrument_subtype1_code="Services"),
        _bop_row(date, "Primary income", primary, form_type, instrument_type_code="Primary income"),
        _bop_row(date, "Secondary income", secondary, form_type, instrument_type_code="Secondary income"),
        _bop_row(date, "Current account", goods + services + primary + secondary, form_type),
    ]


def test_bop_history_is_taken_from_481_only_before_324_and_only_when_it_proves_out(monkeypatch):
    """481 carries 2000 onward but gives two amounts for some recent quarters; its early
    quarters are spliced in only when unambiguous, identity-consistent and equal to 324
    where both publish (audit 2026-09-25)."""
    from fetchers import nbk
    rows = _bop_quarter("2019-10-01", 5.0) + _bop_quarter("2020-01-01", 6.0) + _bop_quarter("2020-04-01", 7.0)
    rows += [_bop_row("2023-04-01", "Goods", 9.0, instrument_type_code="Goods and services", instrument_subtype1_code="Goods"),
             _bop_row("2023-04-01", "Goods", 9.9, instrument_type_code="Goods and services", instrument_subtype1_code="Goods")]
    monkeypatch.setattr(nbk, "_fetch_nbk_form_paginated", lambda form, ind: rows)
    history, note = nbk._bop_history("GOODS", "BOP_GOODS_BALANCE", {"2020-04-01": 7.0, "2023-04-01": 9.0})
    assert history == {"2019-10-01": 5.0, "2020-01-01": 6.0}, note
    # A disagreement with 324 on a shared quarter: no history at all, never a guess.
    history, note = nbk._bop_history("GOODS", "BOP_GOODS_BALANCE", {"2020-04-01": 7.5})
    assert history == {} and "differs" in note
    # Two amounts for an early quarter: no history.
    rows.append(_bop_row("2019-10-01", "Goods", 5.5, instrument_type_code="Goods and services", instrument_subtype1_code="Goods"))
    history, note = nbk._bop_history("GOODS", "BOP_GOODS_BALANCE", {"2020-04-01": 7.0})
    assert history == {} and "two amounts" in note


def test_form_299_real_exchange_rates_are_based_on_december_2016():
    import csv
    root = Path(__file__).resolve().parents[1] / "data" / "processed" / "nbk"
    for ind in ("RER_USD", "RER_RUB", "RER_EUR", "RER_CNY", "REER_EX_OIL", "NEER_EX_OIL"):
        rows = {r["date"]: float(r["value"]) for r in csv.DictReader((root / f"{ind.lower()}.csv").open(encoding="utf-8"))}
        assert rows["2016-12-01"] == 100.0, ind
        assert min(rows) == "1995-01-01", ind
