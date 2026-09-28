"""NBK monetary-survey history from the page "records" JSON (fetchers/nbk_records.py) and the
second-tier banks' balance-account groups 2030/2040/2050 (fetchers/nbk_balance_groups.py).
Parser tests on built fixtures (no network); data tests on the processed files when they exist."""
import csv
import io
import sys
from pathlib import Path

import openpyxl
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from fetchers import nbk_balance_groups as bg, nbk_records as nr  # noqa: E402
from lib import validation  # noqa: E402

DIMS = REPO_ROOT / "data" / "processed" / "dims"


def _zero_record(code: str, reporting_date: str, **values) -> dict:
    """A record of the survey with every field 0 (every identity holds) plus `values`."""
    raw_keys = [("r_m_с_a_s_n_s_o" if k == "r_m_c_a_s_n_s_o" else k) for k in nr.SURVEYS[code].fields]
    rec = {k: 0 for k in raw_keys}
    rec.update(values)
    rec.update({"note_ru": None, "note_kz": None, "note_en": None, "published_at": "2000-01-01 00:00:00",
                "reporting_date": reporting_date})
    return rec


# ---------------------------------------------------------------- nbk_records: structure and dating

def test_every_survey_has_a_fallback_name_per_field_and_parents_are_fields():
    for code, survey in nr.SURVEYS.items():
        assert set(nr.FALLBACK_NAMES[code]) == set(survey.fields), code
        for key, parent in survey.parents.items():
            assert key in survey.fields and (parent.startswith("=") or parent in survey.fields), (code, key)
        for ident in survey.identities:
            assert ident.total in survey.fields and all(k in survey.fields for _, k in ident.terms()), (code, ident)


def test_item_key_latinises_the_cyrillic_c_in_the_nbk_key():
    assert nr.item_key("r_m_с_a_s_n_s_o") == "r_m_c_a_s_n_s_o"
    assert nr.item_key("r_m_с_a_s_n_s_o").isascii()


def test_month_end_record_is_dated_the_first_of_the_next_month():
    rows = [_zero_record("CB", "2023-01-31 00:00:00"), _zero_record("CB", "2022-12-07 00:00:00"),
            _zero_record("CB", "2023-02-03 00:00:00")]
    frame = nr.survey_frame("CB", nr.check_structure("CB", rows))
    assert list(frame) == ["2023-01-01", "2023-02-01", "2023-03-01"]  # 2022-12 -> 2023-01-01


def test_quarterly_survey_dates_and_rejects_a_non_quarter_month():
    frame = nr.survey_frame("OFC", [_zero_record("OFC", "2015-03-05 00:00:00"), _zero_record("OFC", "2026-06-30 22:00:00")])
    assert list(frame) == ["2015-04-01", "2026-07-01"]
    with pytest.raises(validation.StructuralChangeError):
        nr.survey_frame("OFC", [_zero_record("OFC", "2015-04-05 00:00:00")])


def test_known_misdated_banks_record_moves_to_2003_04_and_other_duplicates_stop():
    rows = [_zero_record("ODC", "2005-04-01 00:00:00", d_a=1), _zero_record("ODC", "2005-04-14 00:00:00", d_a=2)]
    frame = nr.survey_frame("ODC", rows)
    assert frame["2003-05-01"]["d_a"] == 2 and frame["2005-05-01"]["d_a"] == 1
    with pytest.raises(validation.StructuralChangeError, match="two records for 2005-04"):
        nr.survey_frame("ODC", [_zero_record("ODC", "2005-04-01 00:00:00"), _zero_record("ODC", "2005-04-20 00:00:00")])


def test_new_or_missing_field_is_a_structural_change():
    rec = _zero_record("FS", "2020-03-31 00:00:00", brand_new=5)
    with pytest.raises(validation.StructuralChangeError, match="brand_new"):
        nr.check_structure("FS", [rec])
    rec = _zero_record("FS", "2020-03-31 00:00:00")
    del rec["o_a_n"]
    with pytest.raises(validation.StructuralChangeError, match="o_a_n"):
        nr.check_structure("FS", [rec])


def test_null_values_are_skipped_not_zeroed():
    frame = nr.survey_frame("CB", [_zero_record("CB", "1999-05-31", n_i_r_national_fund=None)])
    assert "n_i_r_national_fund" not in frame["1999-06-01"]


# ---------------------------------------------------------------- nbk_records: checks

def test_identity_breach_is_reported_and_rounding_tolerated():
    frame = nr.survey_frame("ODC", [_zero_record("ODC", "2010-05-31", r=10, t_a_o_d_w_t_n=7, c_n_c=3, d_a=10, l=10, t_d=10)])
    assert nr.check_identities("ODC", frame) == []
    frame["2010-06-01"]["r"] = 12  # 2 off: within the 3 mln band
    frame["2010-06-01"]["d_a"] = 12
    frame["2010-06-01"]["l"] = 12
    frame["2010-06-01"]["t_d"] = 12
    assert nr.check_identities("ODC", frame) == []
    frame["2010-06-01"]["c_n_c"] = 100
    errors = nr.check_identities("ODC", frame)
    assert len(errors) == 1 and "2010-06-01" in errors[0] and "+t_a_o_d_w_t_n +c_n_c" in errors[0]


def test_identity_exemptions_and_until():
    bad = _zero_record("CB", "2004-07-31", n_i_r=1000, n_e_a=1000, l=1000, o_d=1000)  # n_i_r: the 2004-07 error
    assert nr.check_identities("CB", nr.survey_frame("CB", [bad])) == []
    late = _zero_record("CB", "2026-08-31", n_d_a=600_006, l=600_006, o_d=600_006)  # the unpublished NBK line
    assert nr.check_identities("CB", nr.survey_frame("CB", [late])) == []
    early = _zero_record("CB", "2008-12-31", n_d_a=600_006, l=600_006, o_d=600_006)
    assert any("n_d_a" in e for e in nr.check_identities("CB", nr.survey_frame("CB", [early])))


def test_cross_survey_nbfi_identity():
    frames = {"CB": nr.survey_frame("CB", [_zero_record("CB", "2011-12-31", n_d_a_r_non_banking=146_208)]),
              "ODC": nr.survey_frame("ODC", [_zero_record("ODC", "2011-12-31", r_f_n_b_f_i=315_671, h_r=5)]),
              "BS": nr.survey_frame("BS", [_zero_record("BS", "2011-12-31", i_a_r_nb_f_o=461_879, i_a_r_h=5)])}
    assert nr.check_cross(frames) == []
    frames["BS"]["2012-01-01"]["i_a_r_nb_f_o"] = 461_000
    assert len(nr.check_cross(frames)) == 1
    frames["BS"]["2012-01-01"]["i_a_r_h"] = 2_982  # 2001-12..2002-09 breaks are before CROSS_FROM only
    assert len(nr.check_cross(frames)) == 2
    old = {c: {"2002-01-01": f["2012-01-01"]} for c, f in frames.items()}
    assert nr.check_cross(old) == []


def test_cb_lines_must_equal_form_50_and_ofc_form_26():
    frame = nr.survey_frame("CB", [_zero_record("CB", "2023-01-31", n_d_a_r_non_banking=5_089_785)])
    form50 = {("2023-02-01", "2.4"): 5_089_785.447, ("2023-02-01", "2.5"): 0.3}
    errors, n = nr.check_against_forms("CB", frame, form50=form50)
    assert errors == [] and n == 2
    errors, _ = nr.check_against_forms("CB", frame, form50={("2023-02-01", "2.4"): 5_000_000.0})
    assert len(errors) == 1 and "line 2.4" in errors[0]
    ofc = nr.survey_frame("OFC", [_zero_record("OFC", "2026-06-30 22:00:00", n_e_a=8_720_303, n_e_a_r_nr=8_720_303)])
    errors, n = nr.check_against_forms("OFC", ofc, form26={"n_e_a": {"2026-07-01": 8_720_303.166}})
    assert errors == [] and n == 1


def test_parse_labels_from_the_page_trans_dictionary():
    html = '''"trans": {
        "note": "Примечание",
        "n_e_a": "Чистые внешние активы",
        "n_d_a_r_non_banking": "Требования к небанковским финансовым организациям",
        "r_m_с_a_s_n_s_o": "Текущие счета  государственных\tнефинансовых организаций",
        "n_i_r": "monetaryreview::monetaryreview.n_i_r",
        "n_e_a": "Net external assets",
    }'''
    labels = nr.parse_labels(html, nr.CB.fields)
    assert labels == {"n_e_a": "Чистые внешние активы",
                      "n_d_a_r_non_banking": "Требования к небанковским финансовым организациям",
                      "r_m_c_a_s_n_s_o": "Текущие счета государственных нефинансовых организаций"}


def test_item_names_qualify_short_or_repeated_labels_with_the_parent():
    names = nr.item_names("ODC", nr.FALLBACK_NAMES["ODC"])
    assert names["l_o"] == "Пассивы: Кредиты"
    assert names["r_f_s_n_f_o"] == "Требования к государственным нефинансовым организациям"
    names = nr.item_names("CB", nr.FALLBACK_NAMES["CB"])
    assert names["n_d_a_requirement"] == "Чистые требования к Центральному Правительству: Требования"
    names = nr.item_names("OFC", nr.FALLBACK_NAMES["OFC"])
    assert names["c"] == "Пассивы: Кредиты" and names["n_e_a_c"].endswith("Требования к нерезидентам: Кредиты")
    assert len(set(names.values())) == len(names)


def test_fetch_offline(monkeypatch, tmp_path):
    monkeypatch.setattr(nr.raw_store, "RAW_ROOT", tmp_path / "raw")
    (tmp_path / "raw" / "nbk").mkdir(parents=True)
    monkeypatch.setattr(nr, "FORM50_PATH", tmp_path / "missing.csv")
    monkeypatch.setattr(nr, "_RECORDS", {
        "CB": [_zero_record("CB", "2021-12-31", n_d_a_r_non_banking=5_317_553, n_d_a=5_317_553, l=5_317_553,
                            o_d=5_317_553)],
        "ODC": [_zero_record("ODC", "2021-12-31")],
        "BS": [_zero_record("BS", "2021-12-31", i_a_r_nb_f_o=5_317_553, i_a=5_317_553, l=5_317_553, l_c_c=5_317_553)]})
    monkeypatch.setattr(nr, "_LABELS", {"CB": {"n_d_a_r_non_banking": "Требования к НФО (с сайта)"}})
    records, manifest = nr.fetch({"id": "NBK_SURVEY_HISTORY", "survey": "CB"})
    by_code = {r["item_code"]: r for r in records}
    assert len(records) == len(nr.CB.fields)
    assert by_code["CB.n_d_a_r_non_banking"] == {"date": "2022-01-01", "region": "national",
                                                 "item_code": "CB.n_d_a_r_non_banking",
                                                 "item_name": "Чистые внутренние активы: Требования к НФО (с сайта)",
                                                 "value": 5_317_553.0}
    assert "CB.r_m_c_a_s_n_s_o" in by_code
    assert by_code["CB.n_d_a_r_rest_economy"]["item_name"] == "Требования к остальной экономике"
    assert manifest["frequency"] == "monthly" and manifest["source_url"].endswith("/records")
    assert any("no label on the page" in w for w in manifest["warnings"])
    assert any((tmp_path / "raw" / "nbk").glob("nbk_nbk_survey_history_*.manifest.json"))


def test_fetch_stops_on_a_broken_cross_identity(monkeypatch, tmp_path):
    monkeypatch.setattr(nr.raw_store, "RAW_ROOT", tmp_path / "raw")
    (tmp_path / "raw" / "nbk").mkdir(parents=True)
    monkeypatch.setattr(nr, "FORM50_PATH", tmp_path / "missing.csv")
    monkeypatch.setattr(nr, "_RECORDS", {
        "CB": [_zero_record("CB", "2021-12-31")], "ODC": [_zero_record("ODC", "2021-12-31", r_f_n_b_f_i=7, d_a=7, l=7, t_d=7)],
        "BS": [_zero_record("BS", "2021-12-31")]})
    monkeypatch.setattr(nr, "_LABELS", {c: dict(nr.FALLBACK_NAMES[c]) for c in nr.SURVEYS})
    with pytest.raises(validation.StructuralChangeError, match="BS i_a_r_nb_f_o"):
        nr.fetch({"id": "BANKS_SURVEY_HISTORY", "survey": "ODC"})


# ---------------------------------------------------------------- nbk_balance_groups

OLD_NAMES = {"2030": "Займы, полученные от Правительства Республики Казахстан, местных исполнительных органов "
                     "Республики Казахстан и национального управляющего холдинга (2030)",
             "2040": "Займы, полученные от международных финансовых организаций (2040)",
             "2050": "Займы, полученные от других банков и организаций, осуществляющих отдельные виды банковских операций (2050)"}
NEW_2030 = ("Займы, полученные от Правительства Республики Казахстан, местных исполнительных органов Республики "
            "Казахстан, национального управляющего холдинга и специального фонда развития частного предпринимательства")
FILLER = [f"Группа {c} ({c})" for c in range(1000, 1011)]


def _old_sheet(values: list[tuple[str, float, float, float]], total=None) -> list[list]:
    rows = [[None], ["Сведения об остатках на счетах банков второго уровня"], [None],
            ["№", "Наименование БВУ", *FILLER, OLD_NAMES["2030"], OLD_NAMES["2040"], OLD_NAMES["2050"]]]
    for i, (bank, a, b, c) in enumerate(values, 1):
        rows.append([i, bank, *[1] * len(FILLER), a, b, c])
    sums = total or [sum(v[k] for v in values) for k in (1, 2, 3)]
    rows.append([None, "Итого", *[len(values)] * len(FILLER), *sums])
    return rows


def _new_sheet(values, name2030=NEW_2030) -> list[list]:
    codes = list(range(1000, 1011))
    rows = [[None], ["Сведения об остатках"], [None], ["№", "Наименование БВУ", "Номера и наименование групп счетов"],
            [None, None, *codes, 2030, 2040, 2050],
            [None, None, *[f"Группа {c}" for c in codes], name2030, OLD_NAMES["2040"][:-7], OLD_NAMES["2050"][:-7]]]
    for i, (bank, a, b, c) in enumerate(values, 1):
        rows.append([i, bank, *[1] * len(codes), a, b, c])
    rows.append([None, "ИТОГ", *[len(values)] * len(codes), *[sum(v[k] for v in values) for k in (1, 2, 3)]])
    return rows


def _xlsx(sheets: dict[str, list[list]]) -> bytes:
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name, rows in sheets.items():
        ws = wb.create_sheet(name)
        for r in rows:
            ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_old_layout_totals_in_million_and_zo_sheet_wins():
    content = _xlsx({"01.01.2010": _old_sheet([("A", 40_000_000, 1, 1_000_000_000), ("B", 7_500_000, 0, 242_700_000)]),
                     "01.01.2010 с ЗО": _old_sheet([("A", 40_000_000, 1, 1_000_000_000), ("B", 7_500_000, 0, 243_100_000)]),
                     "01.02.2010 ": _old_sheet([("A", 47_300_000, 2, 5)])})
    recs = bg.workbook_records(content, 2010)
    v = {(r["date"], r["item_code"]): r["value"] for r in recs}
    assert v[("2010-01-01", "G2030")] == 47_500.0
    assert v[("2010-01-01", "G2050")] == 1_243_100.0  # final turnovers, not 1 242 700
    assert v[("2010-02-01", "G2040")] == 0.002
    assert {r["item_code"] for r in recs} == {"G2030", "G2040", "G2050"} and len(recs) == 6


def test_new_layout_with_the_2023_damu_wording():
    content = _xlsx({"01.02.2023 ": _new_sheet([("A", 200_000_000, 71_100_000, 575_500_000), ("B", 11_897_764, 0, 0)])})
    recs = bg.workbook_records(content, 2023)
    assert {r["item_code"]: r["value"] for r in recs}["G2030"] == pytest.approx(211_897.764)


def test_total_row_must_equal_the_bank_rows():
    content = _xlsx({"01.03.2011": _old_sheet([("A", 10, 20, 30)], total=[10, 20, 31_000])})
    with pytest.raises(validation.StructuralChangeError, match="group 2050 total"):
        bg.workbook_records(content, 2011)


def test_unknown_group_wording_and_wrong_sheet_names_stop():
    content = _xlsx({"01.01.2027": _new_sheet([("A", 1, 2, 3)], name2030="Займы, полученные от Правительства РК и прочих")})
    with pytest.raises(validation.StructuralChangeError, match="group 2030 is now named"):
        bg.workbook_records(content, 2027)
    content = _xlsx({"01.01.2012": _old_sheet([("A", 1, 2, 3)])})
    with pytest.raises(validation.StructuralChangeError, match="is not «01.MM.2013»"):
        bg.workbook_records(content, 2013)
    content = _xlsx({"01.01.2012 (пред.)": _old_sheet([("A", 1, 2, 3)])})
    with pytest.raises(validation.StructuralChangeError, match="unknown sheet suffix"):
        bg.workbook_records(content, 2012)


def test_discovery_of_year_tabs_and_the_balance_file():
    html = '''<a class="tab-nav__link" href="/ru/news/banks-performance/rubrics/2381">2026</a>
    <a class="tab-nav__link" href="/ru/news/banks-performance/rubrics/1949">2017</a>
    <a class="link-black" href="/file/download/89386" download> Сведения о выполнении пруденциальных нормативов </a>
    <a class="link-black" href="/file/download/135281" download> Сведения об остатках на балансовых и
      внебалансовых счетах банков второго уровня_2026 </a>'''
    assert bg.year_rubrics(html) == {2026: "2381", 2017: "1949"}
    assert bg.balance_file_link(html) == "/file/download/135281"


# ---------------------------------------------------------------- data (after the integrator's run)

def _dims(name: str) -> dict[tuple[str, str], float]:
    with (DIMS / f"{name}.csv").open(encoding="utf-8") as f:
        return {(r["date"], r["item_code"]): float(r["value"]) for r in csv.DictReader(f)}


@pytest.mark.skipif(not (DIMS / "nbk_survey_history.csv").exists(), reason="NBK_SURVEY_HISTORY not built yet")
def test_nbk_survey_history_published_figures():
    v = _dims("nbk_survey_history")
    assert v[("2012-01-01", "CB.n_d_a_r_non_banking")] == 146_208
    assert v[("2022-01-01", "CB.n_d_a_r_non_banking")] == 5_317_553
    assert v[("2015-07-01", "CB.n_d_a_r_rest_economy")] == 821_820
    assert min(d for d, _ in v) == "1998-01-01"


@pytest.mark.skipif(not (DIMS / "banks_survey_history.csv").exists(), reason="BANKS_SURVEY_HISTORY not built yet")
def test_banks_survey_history_published_figures():
    v = _dims("banks_survey_history")
    assert v[("2012-01-01", "ODC.r_f_s_n_f_o")] == 897_205
    assert v[("2022-01-01", "ODC.l_o")] == 2_152_007
    assert v[("2003-05-01", "ODC.d_a")] == 836_719  # the misdated record


@pytest.mark.skipif(not (DIMS / "ofc_survey.csv").exists(), reason="OFC_SURVEY not built yet")
def test_ofc_survey_published_figures():
    v = _dims("ofc_survey")
    assert v[("2015-04-01", "OFC.r_o_s_r_s_nf_o")] == 438_758
    assert v[("2022-01-01", "OFC.r_o_s_r_s_nf_o")] == 966_553


@pytest.mark.skipif(not (DIMS / "banks_gov_holding_borrowings.csv").exists(),
                    reason="BANKS_GOV_HOLDING_BORROWINGS not built yet")
def test_banks_gov_holding_borrowings_published_figures():
    v = _dims("banks_gov_holding_borrowings")
    assert v[("2015-01-01", "G2030")] == pytest.approx(399_800, abs=100)
    assert v[("2023-02-01", "G2030")] == pytest.approx(211_900, abs=100)
    assert v[("2023-01-01", "G2050")] == pytest.approx(742_600, abs=100)
