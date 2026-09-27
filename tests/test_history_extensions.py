"""History added 2026-09-27: the state budget monthly and quarterly from the Minfin bulletin
archive, core inflation 2011-2022 (Taldau 703082), retail volume by goods group from 2016
(Taldau 702041), bank loans by type from 1996 (NBK historical file), and the CPI publication's
latest month in project_knowledge."""
import csv
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from fetchers import minfin  # noqa: E402


def _series(agency: str, indicator: str) -> dict[str, float]:
    with (REPO_ROOT / "data" / "processed" / agency / f"{indicator.lower()}.csv").open(encoding="utf-8") as f:
        return {r["date"]: float(r["value"]) for r in csv.DictReader(f) if r["value"]}


# ---------------------------------------------------------------- state budget

def test_state_budget_quarters_from_ytd_and_annual():
    ytd = {"2025-03-31": 10.0, "2025-06-30": 25.0, "2025-09-30": 33.0, "2026-03-31": 12.0, "2026-06-30": 30.0}
    annual = {"2025-12-31": 50.0}
    q = minfin.state_budget_quarters(ytd, annual)
    assert q == {"2025-01-01": 10.0, "2025-04-01": 15.0, "2025-07-01": 8.0, "2025-10-01": 17.0,
                 "2026-01-01": 12.0, "2026-04-01": 18.0}
    assert "2026-07-01" not in minfin.state_budget_quarters({"2026-06-30": 1.0}, {})   # never interpolated


def test_ytd_column_found_in_both_table_3_layouts():
    old = [["Атауы", "2016 ж. есеп/ 2016 г. отчет", "2017 ж. есеп", "2018 ж. есеп",
            "2019 ж. қантар-қараша есеп/ 2019 г. январь-ноябрь отчет", "2018 ж. есеп/ 2018 г. отчет", "Наименование"],
           ["", "жылдық/ годовой", "", "", "қантар-қараша/январь-ноябрь", "1-тоқсан/ 1 квартал"]]
    new = [["Атауы", "2023 ж. есеп", "2024 ж. есеп", "2025 ж. есеп", None,
            "2026 ж. қантар-маусым есеп/ 2026 г. январь-июнь отчет", "Наименование"],
           [None, None, None, "жылдық/ годовой", "қантар-маусым/январь-июнь", None]]
    assert minfin._state_budget_ytd_col(old, 2019) == 4
    assert minfin._state_budget_ytd_col(new, 2026) == 5          # not column 4, last year's January-June


def test_state_budget_row_found_in_any_label_column():
    match = minfin._state_budget_row_matcher("I. ДОХОДЫ")
    assert match(["I. КІРІСТЕР", 1.0, 2.0, "I. ДОХОДЫ"])                      # column G, current layout
    assert match(["I. КІРІСТЕР"] + [1.0] * 9 + ["I. ДОХОДЫ"])                # column K, 2019-2021
    assert not match(["II. ШЫҒЫНДАР", 1.0, "II. ЗАТРАТЫ"])


def test_state_budget_history_reaches_2019_and_quarters_add_up():
    ytd = _series("minfin", "STATE_BUDGET_REVENUE_YTD")
    assert min(ytd) <= "2019-01-31" and len(ytd) >= 75
    annual = _series("minfin", "STATE_BUDGET_REVENUE")
    assert min(annual) <= "2016-12-31"
    q = _series("minfin", "STATE_BUDGET_REVENUE_Q")
    for year in range(2019, 2026):
        four = [q.get(f"{year}-{m}-01") for m in ("01", "04", "07", "10")]
        if None not in four:
            assert abs(sum(four) - annual[f"{year}-12-31"]) < 1.0
    # the 2020-21 bulletins printed these quarters directly: 2019 Q1-Q3, 2020 Q1-Q4
    printed = {"2019-01-01": 2926932, "2019-04-01": 3275941.87, "2019-07-01": 3036024.25,
               "2020-01-01": 3340776.997, "2020-04-01": 3728778.448, "2020-07-01": 3173222.377, "2020-10-01": 4278413.0}
    assert all(abs(q[d] - v) < 1.0 for d, v in printed.items())


def test_bulletin_series_kept_their_recent_values():
    """The archive added history only: the 2025-26 editions' values are those stored before."""
    land = _series("minfin", "LAND_TAX")
    assert min(land) <= "2019-01-31" and max(land) >= "2026-07-31"


# ---------------------------------------------------------------- prices, retail

def test_core_inflation_from_2011_chains_to_year_on_year():
    mom, yoy = _series("bns", "CORE_CPI_MOM_EX3"), _series("bns", "CORE_CPI_YOY_EX3")
    assert min(mom) == "2011-01-01" and min(yoy) == "2011-01-01"
    dates = sorted(mom)
    for i in range(12, len(dates)):
        chained = 100.0
        for d in dates[i - 11:i + 1]:
            chained *= mom[d] / 100
        assert abs(chained - yoy[dates[i]]) < 0.8, dates[i]


def test_retail_volume_by_group_from_2016():
    total = _series("bns", "RETAIL_TRADE_INDEX_MONTHLY")
    food, nonfood = _series("bns", "RETAIL_TRADE_INDEX_FOOD_MONTHLY"), _series("bns", "RETAIL_TRADE_INDEX_NONFOOD_MONTHLY")
    assert min(total) == min(food) == min(nonfood) == "2016-01-01"
    assert abs(total["2026-04-01"] - 105.0) < 0.1                    # Taldau 104.96, the bulletin 105.0


# ---------------------------------------------------------------- bank loans

def test_bank_loans_breakdowns_add_up_and_match_form_445():
    s = {k: _series("nbk", f"BANK_LOANS_STB_{k}") for k in
         ("TOTAL", "KZT", "FX", "LEGAL_ENTITIES", "INDIVIDUALS", "BUSINESS", "HOUSEHOLDS")}
    assert min(s["TOTAL"]) == "1996-02-01" and min(s["BUSINESS"]) == "2003-02-01"
    for a, b in (("KZT", "FX"), ("LEGAL_ENTITIES", "INDIVIDUALS"), ("BUSINESS", "HOUSEHOLDS")):
        common = [d for d in s["TOTAL"] if d in s[a] and d in s[b]]
        assert common and all(abs(s[a][d] + s[b][d] - s["TOTAL"][d]) < 2 for d in common)
    kzt, fx = _series("nbk", "LOANS_INDIVIDUALS_KZT"), _series("nbk", "LOANS_INDIVIDUALS_FX")
    common = [d for d in s["HOUSEHOLDS"] if d in kzt and d in fx]
    assert len(common) >= 40 and all(abs(s["HOUSEHOLDS"][d] - kzt[d] - fx[d]) < 1 for d in common)


# ---------------------------------------------------------------- project knowledge

def test_cpi_detail_snapshot_is_one_row_per_item_and_region():
    with (REPO_ROOT / "project_knowledge" / "latest" / "cpi_detail_latest.csv").open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    keys = [(r["region"], r["item_code"]) for r in rows]
    assert len(keys) == len(set(keys)) and len({r["date"] for r in rows}) == 1
    total = next(r for r in rows if r["region"] == "national" and r["item_code"] == "TOTAL")
    assert float(total["mom"]) > 90 and total["contrib_mom_pp"] != ""
    assert sum(r["region"] != "national" for r in rows) >= 60 and any(r["item_code"] == "CORE_EX3" for r in rows)


# ---------------------------------------------------------------- bulletin gaps, December, non-oil deficit (2026-09-27, second pass)

def test_period_headers_in_both_word_orders():
    assert minfin._period_of("2026 ж. қаңтар-шілде/ январь-июль отчет 2026 г.") == (2026, 7)
    assert minfin._period_of("2019 ж. қантар-қараша есеп/ 2019 г. январь-ноябрь отчет") == (2019, 11)
    assert minfin._period_of("январь-декабрь отчет 2023 г.") == (2023, 12)
    assert minfin._period_of("2023ж. есеп/ отчет 2023г.") is None


def test_ytd_column_in_february_2020_and_in_december_editions():
    feb_2020 = [["Атауы", "2018 ж. есеп/ 2018 г. отчет", "2019ж. есеп/ отчет 2019г.", "2020ж. есеп/ отчет 2020г.",
                 "2019 ж. есеп/ 2019 г. отчет", "2019 ж. есеп/ 2019 г. отчет"],
                [None, "жылдық/ годовой", "жылдық/ годовой", "қантар/ январь", "1-тоқсан/\n1 квартал", "2-тоқсан/\n2 квартал"]]
    assert minfin._state_budget_ytd_col(feb_2020, 2020, 1) == 3
    december = [["Атауы", "2021ж. есеп/ 2021г. отчет", "2022 ж. есеп/ 2022 г. отчет", "2023ж. есеп/ отчет 2023г.", "Наименование"]]
    assert minfin._state_budget_ytd_col(december, 2023, 12) == 3
    assert minfin._state_budget_ytd_col(december, 2023, 11) is None
    with_quarters = [["Атауы", "2019ж. есеп/ отчет 2019г.", "2019 ж. есеп/ 2019 г. отчет"], [None, "жылдық/ годовой", "4-тоқсан/ 4 квартал"]]
    assert minfin._state_budget_ytd_col(with_quarters, 2019, 12) == 1


def test_row_label_skips_trailing_empty_cells():
    assert minfin._row_label(["L01", "110", None, "Жалақы", 1.0, "Заработная плата", None, None]) == "Заработная плата"
    assert minfin._label_matcher("Пенсии")(["1", "323", "Зейнетақы", 5.0, "Пенсии", None])


def test_non_oil_deficit_identity_and_the_copied_financing_row(monkeypatch):
    deficit = {"2019-03-31": -100.0, "2019-12-31": -300.0}
    got = minfin.non_oil_by_identity(deficit, {"2019-03-01": 400.0, "2019-12-01": 900.0}, {"2019-03-31": 50.0})
    assert got == {"2019-03-31": -550.0}
    monkeypatch.setattr(minfin, "_processed_history", lambda i: {"D": deficit, "NF_TRANSFERS_YTD": {"2019-12-01": 900.0}}[i])
    out, replaced = minfin._non_oil_with_identity([{"date": "2019-12-31", "value": 300.0}], "D", {"2019-12-31": 80.0})
    assert replaced == ["2019-12-31"] and out == [{"date": "2019-12-31", "value": -1280.0}]


def test_budget_series_now_cover_december_and_2019_2021():
    rev_ytd, rev = _series("minfin", "STATE_BUDGET_REVENUE_YTD"), _series("minfin", "STATE_BUDGET_REVENUE")
    for y in range(2019, 2026):
        assert abs(rev_ytd[f"{y}-12-31"] - rev[f"{y}-12-31"]) < 1.0, y
    nod = _series("minfin", "STATE_NON_OIL_DEFICIT_YTD")
    assert min(nod) == "2018-01-31" and len(nod) >= 95                            # NF transfers start in 2018
    d, tr, duty = (_series("minfin", i) for i in ("STATE_BUDGET_DEFICIT_YTD", "NF_TRANSFERS_YTD", "OIL_EXPORT_DUTY"))
    tr = {k[:7]: v for k, v in tr.items()}
    printed = [k for k in nod if k >= "2022-04" and k[5:7] != "12" and k in duty and k[:7] in tr]
    assert len(printed) > 40 and all(abs(nod[k] - (d[k] - tr[k[:7]] - duty[k])) < 1.0 for k in printed)
    annual = _series("minfin", "STATE_NON_OIL_DEFICIT")
    assert all(v < 0 for v in annual.values())                                   # 2019-2021 were +financing
    for sid in ("GOV_WAGES_EXPENDITURE", "GOV_SUBSIDIES_EXPENDITURE", "CUSTOMS_DUTIES", "LOCAL_GOV_SUBSIDIES_EXPENDITURE"):
        assert len(_series("minfin", sid)) >= 85, sid


def test_yearly_archives_extend_the_state_budget_to_2013():
    rev, exp, dfc = (_series("minfin", i) for i in ("STATE_BUDGET_REVENUE_YTD", "STATE_BUDGET_EXPENDITURE_YTD", "STATE_BUDGET_DEFICIT_YTD"))
    lend, fa = _series("minfin", "STATE_NET_BUDGET_LENDING_YTD"), _series("minfin", "STATE_FINANCIAL_ASSETS_BALANCE_YTD")
    assert min(rev) == "2013-01-31" and sum(d < "2019" for d in rev) >= 68
    assert abs(rev["2017-06-30"] - 5010193.2) < 0.1                               # «на 1 июля 2017», табл 3
    early = [d for d in rev if d < "2019" and all(d in x for x in (exp, dfc, lend, fa))]
    assert len(early) >= 68 and all(abs(rev[d] - exp[d] - lend[d] - fa[d] - dfc[d]) < 1.5 for d in early)
    annual = _series("minfin", "STATE_BUDGET_REVENUE")
    assert all(abs(rev[f"{y}-12-31"] - annual[f"{y}-12-31"]) < 1.0 for y in (2016, 2017, 2018))
    q = _series("minfin", "STATE_BUDGET_REVENUE_Q")
    assert min(q) == "2013-01-01" and abs(sum(q[f"2017-{m}-01"] for m in ("01", "04", "07", "10")) - annual["2017-12-31"]) < 1.0
    assert min(_series("minfin", "GOV_WAGES_EXPENDITURE")) == "2013-01-31"
