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


def _goods(date, amount):
    return _bop_row(date, "Goods", amount, instrument_type_code="Goods and services", instrument_subtype1_code="Goods")


def test_bop_quarters_come_from_481_with_324_filling_in(monkeypatch):
    """481 carries 2000 on and, since 2026-10-16, the NBK's current vintage; 324 lagged it
    (2023 unrevised, 2025-Q3 missing). Each quarter takes 481's single amount, else 324's."""
    import pytest
    from fetchers import nbk
    from lib import validation
    shared = ["2020-04-01", "2020-07-01", "2020-10-01", "2021-01-01"]
    rows = _bop_quarter("2019-10-01", 5.0) + _bop_quarter("2020-01-01", 6.0)
    for i, d in enumerate(shared):
        rows += _bop_quarter(d, 7.0 + i)
    rows += _bop_quarter("2023-04-01", 9.0)                              # revised in 481
    rows += [_goods("2024-04-01", 3.0), _goods("2024-04-01", 3.3)]       # two vintages in 481
    rows += _bop_quarter("2025-10-01", 4.0)                              # absent from 324
    monkeypatch.setattr(nbk, "_fetch_nbk_form_paginated", lambda form, ind: rows)
    recent = {**{d: 7.0 + i for i, d in enumerate(shared)}, "2023-04-01": 8.5, "2024-04-01": 3.3, "2026-01-01": 2.0}
    recent["2021-01-01"] = 10.0000004                                     # 324's seventh decimal
    merged, note = nbk._bop_merge("GOODS", "BOP_GOODS_BALANCE", recent)
    assert merged == {"2019-10-01": 5.0, "2020-01-01": 6.0, **{d: 7.0 + i for i, d in enumerate(shared)},
                      "2021-01-01": 10.0000004, "2023-04-01": 9.0, "2024-04-01": 3.3, "2025-10-01": 4.0,
                      "2026-01-01": 2.0}, note
    assert "324 differs on 1 report dates (2023-04-01..2023-04-01), 481 taken" in note
    # A different line, not a revision: 481 and 324 disagree on the first shared quarters.
    with pytest.raises(validation.StructuralChangeError, match="not the same line"):
        nbk._bop_merge("GOODS", "BOP_GOODS_BALANCE", {**recent, "2020-04-01": 7.5})
    # Two amounts in 481 and nothing in 324 to decide: stop rather than guess or leave a hole.
    with pytest.raises(validation.StructuralChangeError, match="no amount to decide"):
        nbk._bop_merge("GOODS", "BOP_GOODS_BALANCE", {d: v for d, v in recent.items() if d != "2024-04-01"})
    # The components no longer add up to the current account in 481.
    next(r for r in rows if r["report_date"] == "2019-10-01" and r["code"] == "Current account")["amount"] = 99.0
    with pytest.raises(validation.StructuralChangeError, match="breaks goods"):
        nbk._bop_merge("SERVICES", "BOP_SERVICES_BALANCE", {d: -1.0 for d in shared})
    # 481 gone: the stored series is kept (the fetch fails) instead of being cut to 324's 2020 start.
    monkeypatch.setattr(nbk, "_fetch_nbk_form_paginated", lambda form, ind: [])
    with pytest.raises(validation.StructuralChangeError, match="no row for this line"):
        nbk._bop_merge("GOODS", "BOP_GOODS_BALANCE", recent)


def test_form_299_real_exchange_rates_are_based_on_december_2016():
    import csv
    root = Path(__file__).resolve().parents[1] / "data" / "processed" / "nbk"
    for ind in ("RER_USD", "RER_RUB", "RER_EUR", "RER_CNY", "REER_EX_OIL", "NEER_EX_OIL"):
        rows = {r["date"]: float(r["value"]) for r in csv.DictReader((root / f"{ind.lower()}.csv").open(encoding="utf-8"))}
        assert rows["2016-12-01"] == 100.0, ind
        assert min(rows) == "1995-01-01", ind
