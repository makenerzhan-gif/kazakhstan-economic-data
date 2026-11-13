"""Budget classifications from the Statistical Bulletin (scripts/fetchers/minfin_classification.py, 2026-11-13)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from fetchers import minfin_classification as mc  # noqa: E402
from lib import dims, validation  # noqa: E402

DS = {"id": "BUDGET_EXPENDITURE_ECONOMIC_YTD"}
HEAD = "2026 ж. қаңтар-мамыр/_x000D_ январь-май отчет 2026 г."


def _rep(total="1000", current="800"):
    """«табл 10»: category, subclass, specific, Kazakh name, -, value, Russian name."""
    return [["Cанаты", "Подкласс", "Специфика", "Атауы", None, HEAD, "Наименование"],
            [None, None, None, "БАРЛЫҒЫ", None, total, "ВСЕГО"],
            ["1", None, None, "Ағымдағы", None, current, "Текущие затраты"],
            ["L01 Категория расходов", "110", None, "Жалақы", None, "300", "Заработная плата"],
            ["1", "110", "111", "x", None, "250", "Оплата труда"],
            ["1", None, "112", "x", None, "50", "Дополнительные денежные выплаты"],
            ["L01 Категория расходов", "210", None, "x", None, "100", "Выплаты вознаграждений по внутренним займам"],
            ["L01 Категория расходов", "320", None, "x", None, "400", "Трансферты физическим лицам"],
            ["1", "320", "323", "x", None, "350", "Пенсии"],
            ["2", None, None, "Күрделі", None, "150", "Капитальные затраты"],
            ["L01 Категория расходов", "430", None, "x", None, "150", "Капитальные затраты, направленные на развитие"],
            ["4", None, None, "x", None, "50", "Приобретение финансовых активов"],
            ["L01 Категория расходов", "610", None, "x", None, "50", "Приобретение финансовых активов"]]


def test_economic_lines_codes_and_gfs_bridge():
    lines = mc.economic_lines(_rep(), 5, with_specifics=True)
    by = {c: v for c, _, v in lines}
    assert by == {"TOTAL": 1000, "CAT1": 800, "110": 300, "111": 250, "112": 50, "210": 100, "320": 400, "323": 350,
                  "CAT2": 150, "430": 150, "CAT4": 50, "610": 50}
    mc.check_sums(lines, DS, "test")
    gfs = {c: v for c, _, v in mc.gfs_lines(lines)}
    assert gfs == {"GFS.21": 300, "GFS.24": 100, "GFS.27": 400, "GFS.31": 150, "GFS.32": 50}       # specifics are not counted twice
    state = mc.economic_lines([r[:2] + r[3:] for r in _rep()], 4, with_specifics=False)             # «табл 6» has no specifics column
    assert "111" not in {c for c, _, _ in state} and {c for c, _, _ in state} >= {"TOTAL", "CAT1", "110", "610"}


def test_economic_sum_checks_stop_the_dataset():
    with pytest.raises(validation.StructuralChangeError, match="categories sum"):
        mc.check_sums(mc.economic_lines(_rep(total="1200"), 5, True), DS, "t")
    with pytest.raises(validation.StructuralChangeError, match="subclasses of CAT1"):
        mc.check_sums(mc.economic_lines(_rep(total="1050", current="850"), 5, True), DS, "t")


def test_economic_edition_dates_and_items():
    d, records, notes = mc.economic_edition({"табл 10": _rep(), "Метаданные": [["x"]]}, DS)
    assert d == "2026-05-01" and len(notes) == 2                         # no state and no local sheet in this fixture
    by = {r["item_code"]: r for r in records}
    assert by["REP.323"]["value"] == 350 and by["REP.323"]["item_name"] == "Республиканский бюджет: Пенсии"
    assert by["REP.GFS.21"]["value"] == 300 and by["REP.TOTAL"]["date"] == "2026-05-01"
    assert mc.economic_edition({"табл 1": [["x"]]}, DS) == (None, [], [])


def _t4():
    head = ["Санаты", "Сыныбы", "Сыныпшасы", "Ерешелігі", "Атауы", "2026 ж. қаңтар-мамыр есеп/_x000D_ январь-май отчет 2026 г.", "Наименование"]
    row = lambda v, label: [None, None, None, "06", "x", v, label]       # noqa: E731
    return [head,
            row("880731", "Поступления за использование природных и других ресурсов"),
            row("165", "Налог на сверхприбыль, за исключением поступлений от организаций нефтяного сектора"),
            row("2378", "Бонусы, за исключением поступлений от организаций нефтяногосектора"),
            row("838118", "Налог на добычу полезных ископаемых, за исключением общераспространенных полезных ископаемых"),
            row("3501", "Налог на добычу полезных ископаемых на общераспространенныеполезные ископаемые, подземные воды"),
            row("-5362", "Плата за использование радиочастотного спектра"),
            row("7115", "Платеж по возмещению исторических затрат"),
            row("625499", "Вывозные таможенные пошлины на сырую нефть"),
            row("8308", "Вывозные таможенные пошлины на товары, выработанные из нефти"),
            row("99", "Налог на добычу полезных ископаемых, за исключением общераспространенных полезных ископаемых")]   # a repeat lower down


def test_resource_lines_and_derived_items():
    vals = mc.resource_lines(_t4(), 5)
    assert vals["MET_NON_OIL"] == 838118 and vals["MET_COMMON_MINERALS"] == 3501 and vals["EXPORT_DUTY_CRUDE"] == 625499
    d, records, _ = mc.resource_edition({"табл 4": _t4()}, {"id": "RESOURCE_PAYMENTS_YTD"}, {"2026-05-01": 1_000_000.0})
    by = {r["item_code"]: r["value"] for r in records}
    assert d == "2026-05-01" and by["NON_OIL_SUBSOIL"] == 165 + 2378 + 838118 + 3501 + 7115
    assert by["OIL_SECTOR_NF"] == 1_000_000 and by["OIL_TOTAL"] == 1_000_000 + 625499 + 8308
    _, records, _ = mc.resource_edition({"табл 4": _t4()}, {"id": "R"}, {})          # no National Fund statement for the month
    assert "OIL_TOTAL" not in {r["item_code"] for r in records} and "NON_OIL_SUBSOIL" in {r["item_code"] for r in records}
    with pytest.raises(validation.StructuralChangeError, match="MET_NON_OIL"):
        mc.resource_edition({"табл 4": [r for r in _t4() if "добычу" not in str(r[-1])]}, {"id": "R"}, {})


def test_registration_and_gfs_map():
    import update_dims
    for ds_id, fetcher in (("BUDGET_EXPENDITURE_ECONOMIC_YTD", "minfin_economic"), ("RESOURCE_PAYMENTS_YTD", "minfin_resource")):
        ds = update_dims.DATASETS[ds_id]
        assert ds["fetcher"] == fetcher and fetcher in update_dims.AGENCY_FETCHERS and ds["cumulation"] == "year_to_date"
    spans = sorted(r for ranges in mc.GFS_MAP.values() for r in ranges)
    assert all(a[1] < b[0] for a, b in zip(spans, spans[1:]))            # a subclass maps to one GFS item only
    assert set(mc.GFS_MAP) == set(mc.GFS_NAMES)


def test_processed_economic_classification_adds_up():
    rows = dims.load_processed("BUDGET_EXPENDITURE_ECONOMIC_YTD")
    if not rows:
        pytest.skip("processed file absent")
    by = {}
    for r in rows:
        budget, code = r["item_code"].split(".", 1)
        by.setdefault((budget, r["date"]), {})[code] = float(r["value"])
    assert len(by) >= 30
    for (budget, when), vals in by.items():
        cats = sum(v for c, v in vals.items() if c.startswith("CAT"))
        assert cats == pytest.approx(vals["TOTAL"], rel=1e-4, abs=0.5), (budget, when)
        gfs = sum(v for c, v in vals.items() if c.startswith("GFS."))
        assert gfs == pytest.approx(vals["TOTAL"] - vals.get("CAT6", 0.0), rel=1e-4, abs=0.5), (budget, when)   # all but PPP obligations


@pytest.mark.cross_source
def test_state_wages_equal_the_scalar_series():
    import csv
    rows = dims.load_processed("BUDGET_EXPENDITURE_ECONOMIC_YTD")
    path = Path(__file__).resolve().parents[1] / "data" / "processed" / "minfin" / "state_gov_wages_expenditure.csv"
    if not rows or not path.exists():
        pytest.skip("processed files absent")
    scalar = {r["date"][:7]: float(r["value"]) for r in csv.DictReader(path.open(encoding="utf-8"))}
    common = [(r["date"][:7], float(r["value"])) for r in rows if r["item_code"] == "STATE.110" and r["date"][:7] in scalar]
    assert len(common) >= 10
    for month, value in common:
        assert value == pytest.approx(scalar[month], abs=0.5), month
