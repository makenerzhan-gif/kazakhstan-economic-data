"""Utility-tariff events (2026-09-27): КРЕМ/ДКРЕМ tariff orders and press releases from the gov.kz
content-manager API, the Ministry of Energy's electricity and wholesale-gas price caps from
old.adilet.zan.kz (TARIFF_DECISIONS, scripts/fetchers/krem_tariffs.py), and the months in which
the CPI shows a utility price jump (TARIFF_CHANGE_MONTHS, scripts/fetchers/tariff_jumps.py).
Parser tests on fixtures copied from the live sources; data tests on the processed files when
they exist."""
import csv
import math
import sys
from datetime import date
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from fetchers import krem_tariffs as kt  # noqa: E402
from fetchers import tariff_jumps as tj  # noqa: E402
from lib import dims  # noqa: E402

DIMS = REPO_ROOT / "data" / "processed" / "dims"
ZHM = "Департамент Комитета по регулированию естественных монополий по Жамбылской области"
KRG = "Департамент Комитета по регулированию естественных монополий по Карагандинской области"
ALA = "Департамент Комитета по регулированию естественных монополий по городу Алматы"


def _doc(doc_id, title, organ="", activities=(), created="2026-09-25T18:59:00.000+00:00"):
    return {"id": doc_id, "title": title, "created_date": created,
            "gosorgan": {"items": [{"project_name": organ}] if organ else []},
            "activities": {"items": [{"title": a} for a in activities]}}


# ---------------------------------------------------------------- documents (order titles)

def test_amendment_is_dated_by_its_own_order_not_the_amended_one():
    doc = _doc(1072256, 'Приказ №54-ОД от 24.09.2026 года "О внесении изменений в приказ Департамента Комитета по '
                        'регулированию естественных монополий Министерства национальной экономики Республики Казахстан по '
                        'Жамбылской области от 18 ноября 2022 года №86-ОД "Об утверждении тарифа и тарифной сметы АО '
                        '"Таразэнергоцентр" на услуги по производству тепловой энергии на 2023-2027 годы"', ZHM,
               ["Жамбылская область", "Приказы по тарифам"])
    recs, why = kt.parse_document(doc)
    assert why is None and len(recs) == 1
    r = recs[0]
    assert (r["date"], r["region"], r["item_code"]) == ("2026-10-01", "ZHM", "ZHM.HEAT.AMEND.D1072256")
    assert "приказ №54-ОД от 2026-09-24" in r["item_name"] and "оценка -- месяц после приказа" in r["item_name"]
    assert math.isnan(r["value"])
    assert "/documents/details/1072256" in r["item_name"]


def test_stated_effective_date_wins_over_the_order_date():
    doc = _doc(870001, 'Об утверждении предельных цен на розничную реализацию электрической энергии Филиала АО '
                       '"Алатау Жарык Компаниясы" - "ЭнергоСбыт" с вводом в действие с 15 июля 2025 года', ALA)
    recs, why = kt.parse_document(doc)
    assert why is None
    assert [(r["date"], r["region"], r["item_code"]) for r in recs] == [
        ("2025-07-01", "ALA", "ALA.ELEC_SUPPLY.PRICE_CAP.D870001")]
    assert "вступает в силу 2025-07-15 (указано)" in recs[0]["item_name"]


def test_one_record_per_service_and_two_digit_years():
    doc = _doc(356001, "Приказ № 215-ОД от 20.09.22 г. Об утверждении тарифов и тарифных смет на услуги подачи воды по "
                       "распределительным сетям, отвода и очистки сточных вод ТОО «ПетроКазахстан Ойл Продактс»", ZHM)
    recs, why = kt.parse_document(doc)
    assert why is None
    assert sorted(r["item_code"] for r in recs) == ["ZHM.SEWER.APPROVE.D356001", "ZHM.WATER.APPROVE.D356001"]
    assert {r["date"] for r in recs} == {"2022-10-01"}
    assert "ТОО «ПетроКазахстан Ойл Продактс»" in recs[0]["item_name"]


def test_undated_titles_use_publication_only_where_the_department_publishes_promptly():
    title = "Об утверждении временного компенсирующего тарифа на услуги по отводу сточных вод ГКП «Жамбыл су»"
    assert kt.parse_document(_doc(1, title, ZHM)) == ([], "no_date")
    recs, why = kt.parse_document(_doc(2, title, KRG, created="2025-06-30T15:20:00.000+00:00"))
    assert why is None and recs[0]["date"] == "2025-07-01" and recs[0]["item_code"] == "KRG.SEWER.TEMP_COMP.D2"
    assert "снижение, размер не указан" in recs[0]["item_name"]
    # a midnight timestamp is the 2019-2021 migration of old documents, not a publication date
    assert kt.parse_document(_doc(3, title, KRG, created="2020-01-14T00:00:00.000+00:00")) == ([], "no_date")


@pytest.mark.parametrize("title, reason", [
    ("Протокол публичных слушаний по обсуждению проекта тарифа и тарифной сметы АО «СКРЭК» на регулируемую услугу "
     "по передаче электрической энергии", "not_a_decision"),
    ("Отчет об исполнении тарифной сметы на услуги по передаче и распределению электрической энергии за 2023 год "
     "ТОО \"Энергия Спектр\"", "not_a_decision"),
    ("Об утверждении тарифа и тарифной сметы ТОО «Aktobe minerals» на услуги по предоставлению подъездного пути для "
     "проезда подвижного состава", "out_of_scope"),
    ("Приказ № 180-ОД \"Об утверждении корректировки тарифной сметы на услуги по производству, передаче, распределению "
     "и снабжению тепловой энергией на 2018 год ГКП \"Жанатас-Су-Жылу\"", "estimate_only"),
])
def test_non_decisions_are_skipped(title, reason):
    assert kt.parse_document(_doc(9, title, ZHM)) == ([], reason)


def test_central_committee_orders_are_national():
    doc = _doc(860669, "Приказ № 150-ОД от 7 октября 2024 года Об утверждении временного компенсирующего тарифа на "
                       "услуги по хранению газа АО «Интергаз Центральная Азия»",
               "Комитет по регулированию естественных монополий Министерства национальной экономики Республики Казахстан")
    recs, _ = kt.parse_document(doc)
    assert [(r["region"], r["item_code"], r["date"]) for r in recs] == [
        ("national", "KZ.GAS_STORAGE.TEMP_COMP.D860669", "2024-11-01")]


def test_regions_follow_the_2022_split():
    assert kt.region_of("ГКП «Семей Водоканал»", date(2021, 5, 1)) == "VKO"
    assert kt.region_of("ГКП «Семей Водоканал»", date(2023, 5, 1)) == "ABY"
    assert kt.region_of("по области Абай") == "ABY" and kt.region_of("Абайского района Карагандинской области") == "KRG"
    assert kt.region_of("город Алматы") == "ALA" and kt.region_of("Алматинская область") == "ALM"
    assert kt.region_of("город Нур-Султан") == "AST" and kt.region_of("Южно-Казахстанская область") == "YKO"
    assert kt.region_of("Алматинская область и город Алматы") is None


# ---------------------------------------------------------------- news

SEMEY = {"id": 1163144, "created_date": "2026-02-17T10:00:00.000+00:00",
         "title": "В области Абай снижены тарифы на воду — ГКП «Семей Водоканал» компенсирует потребителям почти 479 млн тенге",
         "body": "<p>В целях защиты прав потребителей приказами Департамента от 11 февраля 2026 года № 7-ОД и № 8-ОД "
                 "утвержден временный компенсирующий тариф сроком на один год с вводом в действие с 1 апреля 2026 года.</p>"
                 "<p>Размер тарифа на услуги по подаче воды по распределительным сетям снижен на 11,78% — с 198,90 тенге "
                 "за м³ до 175,48 тенге за м³. Размер тарифа на услуги по отводу сточных вод снижен на 7,08% — с 137,40 "
                 "тенге за м³ до 127,67 тенге за м³.</p>"
                 "<p>С 1 января 2027 года планируется повышение тарифа на теплоснабжение на 12%.</p>"}


def test_news_takes_the_date_from_the_neighbouring_sentence_and_skips_plans():
    recs, skipped = kt.parse_news(SEMEY)
    got = sorted((r["date"], r["region"], r["item_code"].split(".")[1], r["value"]) for r in recs)
    assert got == [("2026-04-01", "ABY", "SEWER", -7.08), ("2026-04-01", "ABY", "WATER", -11.78)]
    assert skipped.get("plan_or_unchanged") == 1
    assert all(r["item_code"].startswith("ABY.") and ".NEWS.N1163144_" in r["item_code"] for r in recs)


def test_news_value_from_old_and_new_tariff_and_ambiguity():
    assert kt._clause_value("тариф снижен с 85,3 тенге до 76,78 тенге за 1 м3 с НДС или на 10%") == (
        -10.0, "снижение на 10% (указано); с 85,3 до 76,78 тенге")
    v, how = kt._clause_value("основной тариф снижен с 341,48 тенге/1000 м3 до 119,64 тенге/1000 м3")
    assert v == pytest.approx(-64.96, abs=0.01) and "расчёт" in how
    v, how = kt._clause_value("снижение на 0,34% с 31,28 тенге и для бюджета с 75,84 тенге до 64,95 тенге")
    assert math.isnan(v) and how.startswith("неоднозначно")


def test_news_duplicates_keep_the_first_release():
    a = {"item_code": "ABY.WATER.NEWS.N20_1", "_key": ("ABY", "WATER", date(2026, 4, 1), -11.8, "")}
    b = {"item_code": "ABY.WATER.NEWS.N10_1", "_key": ("ABY", "WATER", date(2026, 4, 1), -11.8, "")}
    assert [r["item_code"] for r in kt.dedupe_news([a, b])] == ["ABY.WATER.NEWS.N10_1"]


# ---------------------------------------------------------------- adilet: electricity price caps

HDR = "TITLE: {t} HEADING: Приказ Министра энергетики Республики Казахстан от {d} года № {n}. BODY: "
YEARS = "Предельные тарифы на электрическую энергию по годам 2019 год 2020 год 2021 год 2022 год 2023 год 2024 год 2025 год "


def _act(doc_id, day, num, body, base=False):
    return {"id": doc_id, "base": base, "text": HDR.format(t="t", d=day, n=num) + body}


def test_electricity_caps_chain_mean_change_for_the_effective_year():
    acts = [
        _act("V1", "14 декабря 2018", "514", "Примечание РЦПИ! Вводится в действие с 01.01.2019 Сноска. Предельные тарифы – в "
             "редакции приказа от 26.05.2023 № 192 " + YEARS + "1 1-группа 5,76 5,80 5,90 5,90 7,32 7,32 7,32 ", base=True),
        _act("V2", "22 мая 2022", "100", "Настоящий приказ вводится в действие с 1 июля 2022 года. " + YEARS +
             "1-группа 5,76 5,80 5,90 5,90 5,90 5,90 5,90 2-группа 4,50 5,55 5,59 5,59 5,59 5,59 5,59 "),
        _act("V3", "26 мая 2023", "192", "Примечание ИЗПИ! Вводится в действие с 01.06.2023. " + YEARS +
             "1 1-группа 5,76 5,80 5,90 5,90 7,32 7,32 7,32 2 2-группа 4,50 5,55 5,59 6,17 7,40 7,40 7,40 "),
        _act("V4", "30 сентября 2025", "368-н/қ", "Вводится в действие с 1 октября 2025 года ПРИКАЗЫВАЮ: строку, порядковый "
             "номер 2, изложить в новой редакции: \" 2 2-группа - - - - - - 8,14 \"."),
    ]
    ev = {r["item_code"]: r for r in kt.elec_cap_events(acts)}
    assert list(ev) == ["KZ.ELEC_GEN_CAP.ORDER.V1", "KZ.ELEC_GEN_CAP.ORDER.V2", "KZ.ELEC_GEN_CAP.ORDER.V3",
                        "KZ.ELEC_GEN_CAP.ORDER.V4"]
    assert math.isnan(ev["KZ.ELEC_GEN_CAP.ORDER.V1"]["value"])          # consolidated base: original not visible
    assert math.isnan(ev["KZ.ELEC_GEN_CAP.ORDER.V2"]["value"])          # first table of the chain
    v3 = ev["KZ.ELEC_GEN_CAP.ORDER.V3"]
    assert v3["date"] == "2023-06-01" and v3["region"] == "national"
    assert v3["value"] == pytest.approx(((7.32 / 5.90 - 1) + (7.40 / 5.59 - 1)) / 2 * 100, abs=0.01)
    assert "приказ № 192 от 2023-05-26" in v3["item_name"]
    # a single restated row: group 2 moves 7.40 -> 8.14 (+10%), group 1 unchanged
    assert ev["KZ.ELEC_GEN_CAP.ORDER.V4"]["value"] == pytest.approx(5.0, abs=0.01)


def test_clean_adilet_html_keeps_heading_and_body():
    page = ("<html><head><title>О внесении изменения в приказ № 514 - ИПС \"Әділет\"</title></head><body>"
            "<div>Новый Приказ и.о. Министра энергетики Республики Казахстан от 24 июня 2021 года № 211. Зарегистрирован "
            "в Министерстве юстиции Республики Казахстан 28 июня 2021 года № 23204</div><div>Текст Официальная "
            "публикация Информация</div><a>Печать</a><p>Настоящий приказ вводится в действие с 1 июля 2021 года.</p>"
            "<p>Если Вы обнаружили на странице ошибку, выделите</p></body></html>")
    text = kt.clean_adilet_html(page)
    assert kt._act_header(text) == (date(2021, 6, 24), "211")
    assert kt._act_registered(text) == date(2021, 6, 28)
    assert kt._act_effective(text) == (date(2021, 7, 1), "указано")
    assert "Если Вы обнаружили" not in text


# ---------------------------------------------------------------- adilet: wholesale gas price caps

GAS_2015 = ("TITLE: Об утверждении предельных цен оптовой реализации товарного газа на внутреннем рынке HEADING: Приказ "
            "Министра энергетики Республики Казахстан от 26 декабря 2014 года № 224. BODY: 1. Утвердить прилагаемые "
            "предельные цены оптовой реализации товарного газа на внутреннем рынке Республики Казахстан на период с 1 января "
            "по 30 июня 2015 года. Утверждены приказом Министра Энергетики Предельные цены оптовой реализации товарного газа "
            "на внутреннем рынке Республики Казахстан на период с 1 января по 30 июня 2015 года № п/п Регион Предельная цена "
            "1. Город Алматы 15 881 (пятнадцать тысяч восемьсот восемьдесят один) 2. Алматинская область 15 881 "
            "(пятнадцать тысяч восемьсот восемьдесят один) 3. Южно-Казахстанская область 14 616 (четырнадцать тысяч "
            "шестьсот шестнадцать)")
GAS_2023 = ("TITLE: Об утверждении предельных цен оптовой реализации товарного газа на внутреннем рынке Республики Казахстан "
            "HEADING: Приказ Министра энергетики Республики Казахстан от 6 июня 2023 года № 210. BODY: Приложение 1 "
            "Предельные цены оптовой реализации товарного газа на внутреннем рынке Республики Казахстан Сноска. Приложение 1 – "
            "в редакции приказа Министра энергетики РК от 21.05.2025 № 216-н/қ (вводится в действие после дня его первого "
            "официального опубликования). № Регион Предельная цена на период с 1 июля 2023 года по 30 июня 2024 года на "
            "период с 1 июля 2024 года по 30 июня 2025 года 1. город Астана 27 052 (двадцать семь тысяч пятьдесят два) "
            "29 757 (двадцать девять тысяч семьсот пятьдесят семь) 2. город Алматы 25 103 (двадцать пять тысяч сто три) "
            "29 873 (двадцать девять тысяч восемьсот семьдесят три) Приложение 2 Предельные цены 1. город Алматы 99 999 "
            "(девяносто девять тысяч)")


def test_gas_caps_periods_regions_and_appendix_two_cut():
    periods, prices, note = kt.parse_gas_caps(GAS_2023)
    assert periods == [date(2023, 7, 1), date(2024, 7, 1)]
    assert prices == {"AST": [27052.0, 29757.0], "ALA": [25103.0, 29873.0]}
    assert "216-н/қ" in note
    periods, prices, _ = kt.parse_gas_caps(GAS_2015)
    assert periods == [date(2015, 1, 1)] and prices == {"ALA": [15881.0], "ALM": [15881.0], "YKO": [14616.0]}


def test_gas_cap_events_change_against_the_previous_period():
    ev = kt.gas_cap_events([{"id": "V1400010051", "text": GAS_2015}, {"id": "V2300032715", "text": GAS_2023}],
                           today=date(2024, 1, 1))
    ala = {r["date"]: r for r in ev if r["region"] == "ALA"}
    assert math.isnan(ala["2015-01-01"]["value"])
    assert ala["2023-07-01"]["value"] == pytest.approx((25103 / 15881 - 1) * 100, abs=0.01)
    assert ala["2024-07-01"]["value"] == pytest.approx((29873 / 25103 - 1) * 100, abs=0.01)
    assert ala["2024-07-01"]["transformation"] == "forecast" and "transformation" not in ala["2023-07-01"]
    assert ala["2024-07-01"]["item_code"] == "ALA.GAS_WHOLESALE_CAP.PERIOD.V2300032715_202407"
    keys = [(r["date"], r["region"], r["item_code"]) for r in ev]
    assert len(keys) == len(set(keys))


# ---------------------------------------------------------------- CPI-observed tariff jumps

def test_detect_threshold_and_robust_z():
    series = {f"2020-{m:02d}-01": (100.0 + d, "x") for m, d in zip(range(1, 13), [0, 0.1, 0, -0.1, 0, 0.1, 0, 3.5, 0, 1.6, 0.4, -4])}
    got = {d: (x, rule) for d, x, z, rule, _ in tj.detect(series)}
    assert set(got) == {"2020-08-01", "2020-10-01", "2020-12-01"}
    assert got["2020-08-01"][0] == 3.5 and got["2020-12-01"][0] == -4.0
    assert got["2020-10-01"][1].startswith("робастный z")


def test_chain_later_slug_wins_on_shared_months():
    cpi = {"gaz": {"2008-01-01": 101.0, "2007-12-01": 100.5}, "gazosnabzhenie": {"2008-01-01": 102.0}}
    assert tj.chain(cpi, ["gaz", "gazosnabzhenie"]) == {"2007-12-01": (100.5, "gaz"), "2008-01-01": (102.0, "gazosnabzhenie")}


@pytest.mark.skipif(not (DIMS / "cpi_detail_mom.csv").exists(), reason="CPI_DETAIL_MOM not built")
def test_tariff_jumps_on_the_cpi_file():
    recs, info = tj.fetch({"id": "TARIFF_CHANGE_MONTHS", "frequency": "monthly"})
    got = {(r["item_code"], r["date"]): r["value"] for r in recs}
    assert got[("ELECTRICITY", "2023-08-01")] == pytest.approx(6.7, abs=0.05)
    assert got[("HEATING", "2023-11-01")] == pytest.approx(16.1, abs=0.05)
    assert got[("NETWORK_GAS", "2025-08-01")] == pytest.approx(24.1, abs=0.05)
    assert got[("HOT_WATER", "2019-02-01")] == pytest.approx(-6.6, abs=0.05)
    assert dims.validate(recs, "TARIFF_CHANGE_MONTHS", "monthly").ok


@pytest.mark.skipif(not (DIMS / "tariff_decisions.csv").exists(), reason="TARIFF_DECISIONS not built yet")
def test_tariff_decisions_file():
    with (DIMS / "tariff_decisions.csv").open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) > 2500
    by = {(r["date"], r["region"], r["item_code"]): r for r in rows}
    assert float(by[("2023-06-01", "national", "KZ.ELEC_GEN_CAP.ORDER.V2300032595")]["value"]) == pytest.approx(16.34, abs=0.01)
    gas = by[("2025-07-01", "ALA", "ALA.GAS_WHOLESALE_CAP.PERIOD.V2300032715_202507")]
    assert float(gas["value"]) == pytest.approx(30.7, abs=0.05) and "39 044" in gas["item_name"]
    services = {r["item_code"].split(".")[1] for r in rows}
    assert {"HEAT", "WATER", "SEWER", "ELEC_TRANS", "GAS_DISTR", "ELEC_GEN_CAP", "GAS_WHOLESALE_CAP"} <= services


# ---------------------------------------------------------------- incremental run

def test_incremental_run_keeps_older_documents_and_replaces_the_window(monkeypatch):
    old = [{"date": "2019-08-01", "region": "KST", "item_code": "KST.WATER.TEMP_COMP.D16074", "item_name": "old",
            "value": math.nan},
           {"date": "2026-08-01", "region": "AKM", "item_code": "AKM.WATER.AMEND.D1053445", "item_name": "stale",
            "value": math.nan},
           {"date": "2020-04-01", "region": "ZKO", "item_code": "ZKO.WATER.NEWS.N55589_6", "item_name": "news",
            "value": -3.0}]
    window = [_doc(1053445, "Приказ №103-ОД от 24.07.2026 года О внесении изменений в приказ от 1 марта 2024 года "
                            "«Об утверждении тарифа ГКП «Бурабай Су Арнасы» на услуги по подаче воды по распределительным сетям»",
                   "Департамент Комитета по регулированию естественных монополий  по Акмолинской области")]
    calls = {}
    monkeypatch.setattr(kt, "_stored", lambda: old)
    monkeypatch.setattr(kt, "list_documents", lambda session, since=None: calls.setdefault("since", since) and window)
    monkeypatch.setattr(kt, "list_news", lambda session: [SEMEY])
    monkeypatch.setattr(kt, "_elec_acts", lambda session: [])
    monkeypatch.setattr(kt, "_gas_acts", lambda session: [])
    monkeypatch.setattr(kt, "_save_json", lambda *a, **k: None)
    monkeypatch.setattr(kt.raw_store, "write_download_manifest", lambda *a, **k: None)
    monkeypatch.setattr(kt, "MIN_NEWS", 0)
    monkeypatch.setattr(kt, "MIN_ELEC", 0)
    monkeypatch.setattr(kt, "MIN_GAS", 0)
    recs, info = kt.fetch({"id": "TARIFF_DECISIONS", "frequency": "monthly"})
    assert calls["since"] is not None                      # stored documents -> incremental listing
    codes = {r["item_code"]: r for r in recs}
    assert "KST.WATER.TEMP_COMP.D16074" in codes            # older than the window: kept as stored
    assert codes["AKM.WATER.AMEND.D1053445"]["item_name"] != "stale"   # re-read from the window
    assert codes["AKM.WATER.AMEND.D1053445"]["date"] == "2026-08-01"
    assert "ZKO.WATER.NEWS.N55589_6" not in codes           # news are re-read in full every run
    assert any(c.startswith("ABY.WATER.NEWS.N1163144_") for c in codes)
    assert dims.validate(recs, "TARIFF_DECISIONS", "monthly").ok
