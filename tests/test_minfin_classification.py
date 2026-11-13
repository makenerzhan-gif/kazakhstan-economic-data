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
    for ds_id, fetcher in (("BUDGET_EXPENDITURE_ECONOMIC_YTD", "minfin_economic"), ("RESOURCE_PAYMENTS_YTD", "minfin_resource"),
                           ("BUDGET_RECEIPTS_BY_CODE_YTD", "minfin_receipts")):
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
        assert gfs == pytest.approx(vals["TOTAL"] - vals.get("CAT6", 0.0) - vals.get("CAT5", 0.0), rel=1e-4, abs=0.5), (budget, when)   # all but PPP obligations and (to 2021) debt repayment


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


# ---------------------------------------------------------------- receipts by budget code

L = "L01 Категория дохода"


def _receipts(shift=0, year=2026):
    """«табл 4» (shift 0) or «табл 8 (дох)» (shift 1); 2025 numbers transfers 4, loans 5 and has no special receipts."""
    def row(c, value, label):
        return [None] * shift + list(c) + ["x", value, label]
    head = [[None] * shift + ["Санаты", "Сыныбы", "Сыныпшасы", "Ерешелігі", "Атауы",
                              f"{year} ж. қаңтар-мамыр есеп/_x000D_ январь-май отчет {year} г.", "Наименование"],
            row(("1", "2", "3", "4"), "6", "7"),
            row((None,) * 4, "1450" if year == 2026 else "1400", "ПОСТУПЛЕНИЯ"),
            row((None,) * 4, "1350", "ДОХОДЫ"),
            row(("1", L, L, L), "1000", "Налоговые поступления"),
            row((L, "01", L, L), "600", "Подоходный налог"),
            row((L, L, "1", L), "400", "Корпоративный подоходный налог"),
            row(("1", "01", "1", "10"), "300", "КПН с крупного предпринимательства"),
            row((None, None, None, "11"), "100", "КПН с прочих"),
            row((L, L, "2", L), "200", "Индивидуальный подоходный налог"),
            row((None, None, "2", "01"), "200", "ИПН у источника выплаты"),
            row((L, "05", L, L), "400", "Внутренние налоги на товары, работы и услуги"),
            row((L, L, "3", L), "400", "Поступления за использование природных и других ресурсов"),
            row((None, "05", "3", "06"), "405", "Налог на добычу полезных ископаемых"),
            row((None, None, None, "09"), "-5", "Плата за использование радиочастотного спектра")]
    special = [row(("4", L, L, L), "50", "Специальные поступления"), row((L, "01", L, L), "50", "Специальные поступления"),
               row((L, L, "1", L), "50", "Специальные поступления"), row(("4", "01", "1", "01"), "50", "Плата за негативное воздействие")]
    t, n = ("5", "6") if year == 2026 else ("4", "5")
    tail = [row((t, L, L, L), "350" if year == 2025 else "300", "Поступления трансфертов"),
            row((L, "04", L, L), "350" if year == 2025 else "300", "Трансферты из Национального фонда"),
            row((L, L, "1", L), "350" if year == 2025 else "300", "Трансферты из Национального фонда в республиканский бюджет"),
            row((t, "04", "1", "01"), "350" if year == 2025 else "300", "Гарантированный трансферт"),
            row((n, L, L, L), "100" if year == 2026 else "50", "Погашение бюджетных кредитов"),
            row((L, "01", L, L), "100" if year == 2026 else "50", "Погашение бюджетных кредитов"),
            row((L, L, "1", L), "100" if year == 2026 else "50", "Погашение бюджетных кредитов, выданных из бюджета"),
            row((n, "01", "1", "04"), "100" if year == 2026 else "50", "Погашение кредитов")]
    return head + (special if year == 2026 else []) + tail


def test_receipt_lines_build_the_full_code_from_merged_cells():
    rows = _receipts()
    assert mc._code_offset(rows) == 0 and mc._code_offset(_receipts(shift=1)) == 1
    lines = mc.receipt_lines(rows, 5, 0)
    by = {c: v for c, _, v in lines}
    assert by["TOTAL"] == 1450 and by["REVENUE"] == 1350 and by["1"] == 1000 and by["101"] == 600 and by["1011"] == 400
    assert by["101110"] == 300 and by["101111"] == 100 and by["101201"] == 200          # level codes inherited from the rows above
    assert by["105306"] == 405 and by["105309"] == -5                                   # a refund stays negative
    assert by["401101"] == 50 and by["504101"] == 300 and by["601104"] == 100
    assert "1234" not in "".join(by) and len(lines) == len(by)                          # the numbering row is not a line
    assert mc.check_receipts(lines) == []
    assert {c: v for c, _, v in mc.receipt_lines(_receipts(shift=1), 6, 1)} == by       # the republican sheet is one column to the right


def test_receipt_categories_carry_their_2026_numbers_in_2025():
    by = {c: v for c, _, v in mc.receipt_lines(_receipts(year=2025), 5, 0)}
    assert by["5"] == 350 and by["504101"] == 350 and by["6"] == 50 and by["601104"] == 50 and "4" not in by
    assert mc.check_receipts(mc.receipt_lines(_receipts(year=2025), 5, 0)) == []
    bad = [list(r) for r in _receipts()]
    bad[4][6] = "Новая категория"
    with pytest.raises(ValueError, match="unknown receipt category"):
        mc.receipt_lines(bad, 5, 0)


def test_receipt_sum_breaks_stop_the_dataset():
    rows = [list(r) for r in _receipts()]
    rows[7][5] = "250"                                              # a specific no longer adds up to its subclass
    assert any(b.startswith("1011:") for b in mc.check_receipts(mc.receipt_lines(rows, 5, 0)))
    with pytest.raises(validation.StructuralChangeError, match="1011"):
        mc.receipts_edition({"табл 4": rows}, {"id": "BUDGET_RECEIPTS_BY_CODE_YTD"})
    d, records, notes = mc.receipts_edition({"табл 4": _receipts(), "табл 8 (дох)": _receipts(shift=1)}, {"id": "B"})
    codes = {r["item_code"] for r in records}
    assert d == "2026-05-01" and not notes and {"STATE.105306", "REP.105306", "STATE.TOTAL", "REP.5"} <= codes


def test_processed_receipts_add_up_at_every_level():
    rows = dims.load_processed("BUDGET_RECEIPTS_BY_CODE_YTD")
    if not rows:
        pytest.skip("processed file absent")
    by = {}
    for r in rows:
        budget, code = r["item_code"].split(".", 1)
        by.setdefault((budget, r["date"]), []).append((code, r["item_name"], float(r["value"])))
    assert len(by) >= 20
    import re
    for key, lines in by.items():
        # Above the specifics every level must add up in every stored month. Two things the source itself
        # does are allowed: specifics left out of the printed table (2015-2018) and a «ДОХОДЫ» cell printed
        # as 0, which is not stored (republican budget, January-March 2021).
        real = [b for b in mc.check_receipts(lines) if not re.match(r"\d{4}[: ]", b) and b != "no REVENUE row"]
        assert real == [], key
        vals = {c: v for c, _, v in lines}
        if key[1] < "2026":
            assert "4" not in vals, key                           # before 2026 there is no category 4: transfers sit under the 2026 number 5


@pytest.mark.cross_source
def test_receipts_by_code_equal_the_scalar_tax_series():
    import csv
    rows = dims.load_processed("BUDGET_RECEIPTS_BY_CODE_YTD")
    base = Path(__file__).resolve().parents[1] / "data" / "processed" / "minfin"
    pairs = {"STATE.1": "state_tax_revenue_ytd", "STATE.1011": "state_cit_ytd", "STATE.1012": "state_pit_ytd", "STATE.1051": "state_vat_ytd",
             "STATE.1052": "state_excise_ytd", "STATE.103": "state_social_tax_ytd", "STATE.REVENUE": "state_budget_revenue_ytd",
             "STATE.5": "state_transfers_received_ytd", "STATE.106110": "oil_export_duty"}
    if not rows or not all((base / f"{n}.csv").exists() for n in pairs.values()):
        pytest.skip("processed files absent")
    for code, name in pairs.items():
        scalar = {r["date"][:7]: float(r["value"]) for r in csv.DictReader((base / f"{name}.csv").open(encoding="utf-8")) if r.get("value")}
        common = [(r["date"][:7], float(r["value"])) for r in rows if r["item_code"] == code and r["date"][:7] in scalar]
        assert len(common) >= 10, code
        for month, value in common:
            assert value == pytest.approx(scalar[month], rel=1e-4, abs=1.0), (code, month)


def test_archive_mode_skips_a_broken_edition_and_says_which(monkeypatch):
    """The backfill reads years of older editions: one that does not add up is skipped and named,
    while the daily run still stops on it."""
    from fetchers import minfin
    good, bad = _receipts(), [list(r) for r in _receipts(year=2025)]
    bad[5][5] = "700"                                               # the class 101 no longer equals its subclasses

    class Book:
        def __init__(self, rows):
            self.rows, self.sheetnames = rows, ["табл 4", "табл 1"]
    books = {"new.xlsx": Book(good), "old.xlsx": Book(bad)}
    monkeypatch.setattr(minfin, "_bulletin_documents", lambda: [{"id": 2, "title": "new", "full_text": [{"document": "new.xlsx"}]},
                                                                {"id": 1, "title": "old", "full_text": [{"document": "old.xlsx"}]}])
    monkeypatch.setattr(minfin, "_download", lambda path: path.encode())
    monkeypatch.setattr(minfin, "_open_workbook", lambda content, hint: ("sheets", books[content.decode()]))
    monkeypatch.setattr(minfin, "_iter_rows", lambda kind, wb, name=None: iter(wb.rows if name == "табл 4" else []))
    monkeypatch.setattr(dims, "load_processed", lambda ds_id: [])
    ds = {"id": "BUDGET_RECEIPTS_BY_CODE_YTD"}
    with pytest.raises(validation.StructuralChangeError):
        mc.fetch_receipts(ds)
    monkeypatch.setattr(minfin, "BULLETIN_ARCHIVE", True)
    records, meta = mc.fetch_receipts(ds)
    assert {r["date"] for r in records} == {"2026-05-01"}
    skipped = [w for w in meta["warnings"] if "SKIPPED" in w]
    assert len(skipped) == 1 and "«old»" in skipped[0] and "101:" in skipped[0]
    assert any("sheets:" in w and "табл 1" in w for w in meta["warnings"])        # the missing republican sheet: what is there instead


def test_archive_mode_keeps_an_edition_whose_table_omits_specifics(monkeypatch):
    from fetchers import minfin
    rows = [list(r) for r in _receipts()]
    rows[7][5] = "250"                                              # the subclass 1011 is 400, its printed specifics now give 350
    monkeypatch.setattr(minfin, "BULLETIN_ARCHIVE", True)
    d, records, notes = mc.receipts_edition({"табл 4": rows}, {"id": "B"})
    by = {r["item_code"]: r["value"] for r in records}
    assert by["STATE.1011"] == 400 and by["STATE.101110"] == 250 and any("INCOMPLETE" in n and "1011" in n for n in notes)
    rows[5][5] = "700"                                              # a class that does not add up is a real break
    d, records, notes = mc.receipts_edition({"табл 4": rows}, {"id": "B"})
    assert not records and any(n.startswith("SKIPPED STATE") for n in notes)
