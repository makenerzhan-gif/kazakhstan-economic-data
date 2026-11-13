"""National Fund receipts by budget code from the State Revenue Committee (fetchers/kgd_nf.py)."""
import csv
import io
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from fetchers import kgd_nf, minfin  # noqa: E402
from lib import dims, validation  # noqa: E402

REPO = Path(__file__).resolve().parents[1]


def _workbook(year=2026, months=3, break_total=False) -> bytes:
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "налоги"
    ws.append([f"Receipt of taxes and payments to the National Fund by types of taxes and payments for {year}"])
    ws.append([None] * 13 + ["thousand tenge"])
    ws.append([None, None, "January", "January-February", "January-March"] + ["x"] * 9)
    ws.append([None, "Tax receipts"])
    taxes = {"101105": [100000, 200000, 300000], "105322": [None, None, "5000"], "105325": [1, 2, 3], "105326": [10, 20, 30],
             "105327": [0, 0, 0], "105328": [7, 7, 7], "105329": [None, None, 2]}
    other = {"204201": [1, 1, 1], "204202": [2, 2, 2], "204203": [0, 0, 0], "206111": [0, 0, 0], "303102": [5, 5, 5]}
    def total(block, m):
        return sum(float(v[m] or 0) for v in block.values())
    for code, vals in taxes.items():
        ws.append([code, "tax"] + [str(v) if v is not None else None for v in vals[:months]])
    ws.append([None, "TOTAL tax receipts"] + [str(total(taxes, m) + (1000 if break_total and m == 1 else 0)) for m in range(months)] + ["0"] * (12 - months))
    for code, vals in other.items():
        ws.append([code, "other"] + vals[:months])
    ws.append([None, "TOTAL for the specified positions"] + [str(total(taxes, m) + total(other, m)) for m in range(months)] + ["0"] * (12 - months))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_parse_reads_the_year_from_the_sheet_and_blanks_as_zero():
    year, months, values = kgd_nf.parse_workbook(_workbook())
    assert (year, months) == (2026, 3)
    assert values["CIT"][:3] == [100000, 200000, 300000] and values["EXCESS_PROFIT_TAX"][:3] == [0, 0, 5000]
    assert values["TAX_TOTAL"][2] == 300000 + 5000 + 3 + 30 + 7 + 2 and values["TOTAL"][2] == values["TAX_TOTAL"][2] + 8
    assert kgd_nf.check(year, months, values) == []
    assert any("TAX_TOTAL" in b for b in kgd_nf.check(*kgd_nf.parse_workbook(_workbook(break_total=True))))


def test_fetch_takes_the_fullest_edition_of_a_year_and_skips_one_that_does_not_add_up(monkeypatch):
    books = {"a.xlsx": _workbook(months=2), "b.xlsx": _workbook(months=3), "c.xlsx": _workbook(year=2025, months=3, break_total=True),
             "d.xlsx": _workbook(year=2025, months=1)}
    monkeypatch.setattr(kgd_nf, "_documents", lambda: [{"id": n, "title": "national fund by BCC", "full_text": [{"document": n}]} for n in books])
    monkeypatch.setattr(minfin, "_download", lambda path: books[path])
    monkeypatch.setattr(dims, "load_processed", lambda ds_id: [])
    records, meta = kgd_nf.fetch({"id": "NF_RECEIPTS_BY_CODE_KGD_YTD"})
    by = {(r["item_code"], r["date"]): r["value"] for r in records}
    assert by[("CIT", "2026-03-01")] == 300.0 and ("CIT", "2025-02-01") not in by and by[("CIT", "2025-01-01")] == 100.0   # million tenge
    assert any("SKIPPED" in w and "c.xlsx" in w for w in meta["warnings"])
    monkeypatch.setattr(kgd_nf, "_documents", lambda: [])
    with pytest.raises(validation.StructuralChangeError):
        kgd_nf.fetch({"id": "NF_RECEIPTS_BY_CODE_KGD_YTD"})


def test_title_filter_and_registration():
    assert kgd_nf.TITLE_RE.search("Dynamics of revenues to the national fund for 9 month 2026 year by BCC")
    assert kgd_nf.TITLE_RE.search("Динамика поступлений в Национальный фонд за 9 месяцев 2026 года в разрезе КБК")
    assert not kgd_nf.TITLE_RE.search("Динамика поступлений в государственный бюджет в разрезе КБК")
    import update_dims
    ds = update_dims.DATASETS["NF_RECEIPTS_BY_CODE_KGD_YTD"]
    assert ds["fetcher"] == "kgd_nf" and "kgd_nf" in update_dims.AGENCY_FETCHERS and "kgd" in update_dims.METHODOLOGY


@pytest.mark.cross_source
def test_kgd_equals_the_minfin_statement_at_every_year_end():
    rows = dims.load_processed("NF_RECEIPTS_BY_CODE_KGD_YTD")
    pairs = {"CIT": "nf_oil_cit_ytd", "MET": "nf_met_ytd", "RENT_TAX_EXPORT": "nf_rent_tax_export_ytd", "PSA_SHARE": "nf_psa_share_ytd",
             "EXCESS_PROFIT_TAX": "nf_excess_profit_tax_ytd", "BONUSES": "nf_bonuses_ytd", "TAX_TOTAL": "nf_oil_direct_taxes_ytd"}
    base = REPO / "data" / "processed" / "minfin"
    if not rows or not all((base / f"{n}.csv").exists() for n in pairs.values()):
        pytest.skip("processed files absent")
    for item, name in pairs.items():
        scalar = {r["date"][:7]: float(r["value"]) for r in csv.DictReader((base / f"{name}.csv").open(encoding="utf-8")) if r.get("value")}
        decembers = [(r["date"][:7], float(r["value"])) for r in rows if r["item_code"] == item and r["date"][5:7] == "12" and r["date"][:7] in scalar]
        assert len(decembers) >= 4, item
        for month, value in decembers:
            assert value == pytest.approx(scalar[month], rel=1e-5, abs=1.0), (item, month)
