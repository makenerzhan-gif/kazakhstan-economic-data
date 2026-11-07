"""Sources added 2026-11-07: NBK cubes (loans by industry and purpose, gross FDI, loan quality,
government securities), NBK monetary operations, Taldau prices / tariffs / legal entities / regional
wages, and the hand-kept forecast vintages (Government ПСЭР, NBK rounds). No network."""
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from lib import validation  # noqa: E402
from fetchers import manual_vintages, nbk_cube, nbk_operations, taldau_dims  # noqa: E402
import update_dims  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------- nbk_cube

CUBE = {"id": "T", "form_id": "0", "filters": {"type": "mln"},
        "levels": [["industry"], ["industry", "sub"], ["is_overdue"]],
        "codes": {"industry": {"Manufacturing": "C", "Trade": "G"}, "sub": {"Food": "FOOD", "Other": None},
                  "is_overdue": {"Yes": "OVERDUE", "No": None}},
        "names": {"industry": {"Manufacturing": "Обрабатывающая промышленность"}},
        "total": "TOTAL"}


def _row(industry, sub, overdue, amount, when="2026-09-01", type_="mln"):
    return {"report_date": when, "amount": amount, "type": type_, "industry": industry, "sub": sub, "is_overdue": overdue}


def test_cube_sums_rows_into_levels_and_a_total():
    rows = [_row("Manufacturing", "Food", "No", 10.0), _row("Manufacturing ", "Food", "Yes", 2.0),
            _row("Manufacturing", "Other", "No", 5.0), _row("Trade", None, "No", 7.0),
            _row("Trade", None, "No", 100.0, type_="other unit")]                        # filtered out
    by = {r["item_code"]: r["value"] for r in nbk_cube.cube_records(rows, CUBE)}
    assert by == {"C": 17.0, "G": 7.0, "C.FOOD": 12.0, "OVERDUE": 2.0, "TOTAL": 24.0}
    names = {r["item_code"]: r["item_name"] for r in nbk_cube.cube_records(rows, CUBE)}
    assert names["C"] == "Обрабатывающая промышленность" and names["G"] == "Trade"


def test_cube_stops_on_an_unknown_value():
    with pytest.raises(validation.StructuralChangeError, match="Leasing"):
        nbk_cube.cube_records([_row("Leasing", None, "No", 1.0)], CUBE)


def test_cube_country_map_covers_the_nbk_spellings():
    countries = nbk_cube._countries()
    for name, code in (("USA", "USA"), ("Russia", "RUS"), ("Türkiye", "TUR"), ("The Republic of Korea", "KOR"),
                       ("Hong Kong Special Administrative Region of China", "HKG"), ("Not determined by country", "UNALLOCATED"),
                       ("INTERNATIONAL ORGANIZATIONS", "INTORG"), ("Netherlands", "NLD"), ("China", "CHN")):
        assert countries[nbk_cube._norm(name)][0] == code, name


def test_cube_datasets_are_configured():
    cubes = [d for d in update_dims.DATASETS.values() if d.get("fetcher") == "nbk_cube"]
    assert {d["id"] for d in cubes} >= {"FDI_GROSS_INFLOW_BY_INDUSTRY", "FDI_GROSS_INFLOW_BY_COUNTRY", "LOANS_ISSUED_BY_INDUSTRY",
                                        "LOANS_ISSUED_BY_PURPOSE", "LOANS_STOCK_BY_INDUSTRY", "LOANS_STOCK_BY_PURPOSE",
                                        "LOAN_PORTFOLIO_QUALITY", "GOV_SECURITIES_OUTSTANDING_BY_TYPE"}
    by = {d["id"]: d for d in cubes}
    # flows are stamped with the day after their period (shifted back); stocks keep the NBK's as-at date
    assert by["LOANS_ISSUED_BY_PURPOSE"]["date_basis"] == by["FDI_GROSS_INFLOW_BY_COUNTRY"]["date_basis"] == "next_period_start"
    assert "date_basis" not in by["LOANS_STOCK_BY_PURPOSE"]
    assert by["LOANS_STOCK_BY_PURPOSE"]["codes"]["object_type"]["Construction and purchase of housing by citizens"] == "HOUSING"


# ---------------------------------------------------------------- NBK operations

def test_numbers_as_the_nbk_prints_them():
    assert [nbk_operations.number(s) for s in ("-62,9", "869,8*", "- 1 181 (включая 133,8*)", "2 059 840 000 000", "15,75", "", "-", None, 3.5)] == \
        [-62.9, 869.8, -1181.0, 2059840000000.0, 15.75, None, None, None, 3.5]


def test_intervention_history_matrix_and_mirroring_table():
    html = ("<p>Объем операций НБРК на валютном рынке</p><table><tr><td>Отчетный период</td>"
            + "".join(f"<td>{m}</td>" for m in nbk_operations.MONTHS) + "</tr>"
            + "<tr><td>2014</td>" + "<td>0</td>" * 9 + "<td>-6002,1</td><td></td><td></td></tr>"
            + "<tr><td>2024</td>" + "<td>0</td>" * 10 + "<td>- 1 181 (включая 133,8*)</td><td>-307,6</td></tr></table>"
            + "<table><tr><td colspan='3'>Продажи иностранной валюты для целей монетарной нейтральности (в рамках зеркалирования "
              "операций по реализации права приоритетной покупки аффинированного золота)</td></tr>"
              "<tr><td>Период</td><td>млн долл. США</td><td>млрд тенге</td></tr><tr><td>январь 2025</td><td>464,9</td><td>244</td></tr>"
              "<tr><td>Май2025</td><td>500</td><td>250</td></tr></table>")
    tables = nbk_operations.html_tables(html.encode())
    net = nbk_operations.intervention_matrix(tables)
    assert net["2014-10-01"] == -6002.1 and net["2024-11-01"] == -1181.0 and net["2024-12-01"] == -307.6 and "2014-11-01" not in net
    assert nbk_operations.mirroring(tables) == {"2025-01-01": (464.9, 244.0), "2025-05-01": (500.0, 250.0)}


def test_open_position_days_months_and_identity_fields():
    rows = [{"reporting_date": "2026-11-05 00:00:00", "b": -8705.65, "d": -507.7, "d_r": 0, "r_r": 0, "c_s": 0, "d_a": -6562.75,
             "nbk_a_s_s": 0, "n": -1635.2, "f_c_i_r_s_stb": 0, "i_r_swap_mfi": 0, "r_r_w_m": 0, "stb_l": 0, "f_b_c_a_w_nbk": -4012.41},
            {"reporting_date": "2026-11-04 00:00:00", "b": -8000.0, "d": -500.0, "d_r": 0, "r_r": 0, "c_s": 0, "d_a": -6000.0,
             "nbk_a_s_s": 0, "n": -1500.0, "f_c_i_r_s_stb": 0, "i_r_swap_mfi": 0, "r_r_w_m": 0, "stb_l": 0, "f_b_c_a_w_nbk": -4000.0}]
    days = nbk_operations.record_days(rows)
    day = days["2026-11-05"]
    assert abs(sum(v for c, v in day.items() if c not in ("BALANCE", "CORR_ACCOUNTS")) - day["BALANCE"]) < 1e-9
    names = {code: name for _, code, name in nbk_operations.OPEN_POSITION_ITEMS} | {"CORR_ACCOUNTS": "corr"}
    by = {r["item_code"]: r["value"] for r in nbk_operations.monthly(days, names)}
    assert by["BALANCE.EOM"] == -8705.65 and by["BALANCE.AVG"] == pytest.approx(-8352.825) and by["NOTES.EOM"] == -1635.2


def test_deposit_auctions_monthly_volume_count_and_weighted_yield():
    rows = [("№", "Срок аукциона, дней", "Дата аукциона", "Дата оплаты", "Дата возврата", "Фактический объем размещения, теңге",
             "Спрос, теңге", "Средневзвешенная доходность, %", "Ставка отсечения, %"),
            (1, 7.0, "06.11.2026", "06.11.2026", "13.11.2026", "3 000 000 000 000", "3 000 000 000 000", "16,00", "16,00"),
            (2, 7.0, "05.11.2026", "05.11.2026", "12.11.2026", "1 000 000 000 000", "1 000 000 000 000", "15,00", "15,00")]
    by = {r["item_code"]: r["value"] for r in nbk_operations.auction_months(rows)}
    assert by == {"VOLUME": 4000.0, "N": 2.0, "YIELD": 15.75}


# ---------------------------------------------------------------- Taldau, regional

def test_fetch_regional_flat_city_list_and_stitched_segments(monkeypatch):
    calls = []

    def fake_post(ds, terms, parent="", pos="0", term="741880"):
        calls.append((ds["index_id"], ds["dic_ids"], terms, parent))
        seg2026 = ds["dic_ids"].startswith("68")
        nat = {"id": "741880", "text": "РК", "leaf": "true", "y122025": "104.6", **({"y012026": "99.0"} if seg2026 else {"y012026": "1"})}
        city = {"id": "268012", "text": "Г.АСТАНА", "y122025": "105.0"}
        return [nat, city]

    monkeypatch.setattr(taldau_dims, "_post", fake_post)
    monkeypatch.setattr(taldau_dims.raw_store, "save_raw_bytes", lambda *a, **k: Path("x"))
    monkeypatch.setattr(taldau_dims.raw_store, "write_download_manifest", lambda *a, **k: None)
    ds = {"id": "T", "index_id": "1", "frequency": "monthly", "item_pos": 1, "flat_regions": True, "region_terms": {268012: "AST"},
          "dic_ids": "67,490", "terms": "741880,741916",
          "segments": [{"dic_ids": "67,490", "terms": "741880,741916"}, {"dic_ids": "68,490", "terms": "741880,741916"}],
          "items": [{"code": "TOTAL", "term": "741916", "name": "Грузы"}]}
    recs, _ = taldau_dims.fetch_regional(ds)
    by = {(r["region"], r["date"]): r["value"] for r in recs}
    assert by[("national", "2026-01-01")] == 99.0              # the later segment wins on a common month
    assert by[("AST", "2025-12-01")] == 105.0 and len(calls) == 2  # flat list: no expand call
    ds["region_terms"] = {1: "AST"}
    with pytest.raises(validation.StructuralChangeError, match="268012"):
        taldau_dims.fetch_regional(ds)


def test_fetch_regional_dates_quarters_at_their_first_day():
    assert taldau_dims._region_values({"y062026": "486386", "y032026": "461486"}, "quarterly") == {
        "2026-04-01": 486386.0, "2026-01-01": 461486.0}


# ---------------------------------------------------------------- hand-kept forecast vintages

def test_government_forecast_vintages_are_consistent():
    doc = yaml.safe_load((REPO_ROOT / "config" / "gov_forecast_vintages.yaml").read_text(encoding="utf-8"))
    vintages = doc["vintages"]
    assert len(vintages) >= 27 and len({v["vintage"] for v in vintages}) == len(vintages)
    for v in vintages:
        first = min(v["years"])
        for year, r in v["years"].items():
            assert set(r) <= set(manual_vintages.GOV_FIELDS), (v["vintage"], year)
            if "cpi" in r:
                assert r["cpi"][0] <= r["cpi"][1]
            if year != first and {"gdp_kzt_bn", "gdp_usd_bn", "usdkzt"} <= set(r):
                # GDP in dollars is at the forecast's round exchange rate: the transcription check
                assert abs(r["gdp_kzt_bn"] / r["gdp_usd_bn"] - r["usdkzt"]) < 1.0, (v["vintage"], year)
                assert abs(r["usdkzt"] - round(r["usdkzt"] / 5) * 5) < 0.6, (v["vintage"], year)   # 249.9 = 250 after rounding GDP
    latest = next(v for v in vintages if v["vintage"] == "2026-08")
    assert latest["years"][2027] == {"gdp_kzt_bn": 199348.5, "real_gdp": 105.3, "gdp_usd_bn": 415.3, "usdkzt": 480.0,
                                     "brent": 70.0, "cpi": [7.5, 9.5]}


def test_nbk_forecast_rounds_and_records():
    doc = yaml.safe_load((REPO_ROOT / "config" / "nbk_forecast_rounds.yaml").read_text(encoding="utf-8"))
    rounds = doc["rounds"]
    assert [r["round"] for r in rounds] == sorted(r["round"] for r in rounds) and len(rounds) >= 16
    for r in rounds:
        assert int(r["round"][:4]) == min(r["years"]), r["round"]          # the first year is the current one
    recs = manual_vintages.vintage_records(rounds, "round", manual_vintages.NBK_FIELDS, {"id": "T", "file": "x"})
    by = {(r["item_code"], r["date"]): r["value"] for r in recs}
    assert by[("V2026_08.CPI_LO", "2027-12-31")] == 6.5 and by[("V2026_08.CPI_HI", "2027-12-31")] == 8.5
    assert by[("V2026_08.BRENT", "2026-12-31")] == 89.2 and by[("V2022_12.GDP_HI", "2025-12-31")] == 4.5
    with pytest.raises(validation.StructuralChangeError, match="range"):
        manual_vintages.vintage_records([{"round": "2026-08", "years": {2026: {"gdp": [5, 4]}}}], "round",
                                        manual_vintages.NBK_FIELDS, {"id": "T", "file": "x"})


# ---------------------------------------------------------------- cross-source checks on the stored data

def _stored(name: str) -> dict:
    import csv
    with (REPO_ROOT / "data" / "processed" / "dims" / f"{name}.csv").open(encoding="utf-8") as f:
        return {(r["item_code"], r["region"], r["date"]): float(r["value"]) for r in csv.DictReader(f)}


@pytest.mark.cross_source
def test_form_488_banks_equal_the_nbk_historical_bank_loans():
    import csv
    stb = {k[2]: v for k, v in _stored("loans_stock_by_industry").items() if k[0] == "STB" and k[1] == "national"}
    with (REPO_ROOT / "data" / "processed" / "nbk" / "bank_loans_stb_total.csv").open(encoding="utf-8") as f:
        hist = {r["date"]: float(r["value"]) for r in csv.DictReader(f)}
    common = sorted(set(stb) & set(hist))
    assert len(common) >= 12
    for d in common[-12:]:                                  # the last year: the open-data form and the xlsx agree
        assert abs(stb[d] - hist[d]) <= 1e-6 * hist[d] + 1.0, (d, stb[d], hist[d])


@pytest.mark.cross_source
def test_gross_fdi_totals_by_industry_and_by_country_agree():
    a = {k[2]: v for k, v in _stored("fdi_gross_inflow_by_industry").items() if k[0] == "TOTAL"}
    b = {k[2]: v for k, v in _stored("fdi_gross_inflow_by_country").items() if k[0] == "TOTAL"}
    assert len(a) >= 80 and set(a) == set(b)
    assert all(abs(a[d] - b[d]) < 0.5 for d in a)
