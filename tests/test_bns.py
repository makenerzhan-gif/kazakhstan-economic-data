import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import update_bns


def test_fetchers_registered_for_every_indicator():
    """All 8 BNS stage-1 indicators are confirmed and wired -- this catches a
    typo'd key or an indicator silently falling out of FETCHERS. Does NOT call
    the fetchers themselves (that would hit the network on every test run);
    see tests/test_schema.py etc. for offline coverage of the shared logic
    each fetcher relies on.
    """
    assert set(update_bns.FETCHERS.keys()) == set(update_bns.INDICATOR_IDS)
    for indicator_id, fn in update_bns.FETCHERS.items():
        assert callable(fn), f"{indicator_id}'s fetcher is not callable"


def _xlsx(sheet: str, rows: list[list]) -> bytes:
    import io
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_labour_block_reads_quarters_and_a_footnoted_year():
    """Element 5830 heads 2014 as '20142)'; read as 2013 it duplicated four quarters."""
    from fetchers import bns
    content = _xlsx("ОИРТ", [
        ["Занятое население"], ["тыс."], ["Наименование региона", 2013, None], [None, "I квартал", "год"],
        ["Республика Казахстан", 8000, 8100],
        [" Уровень безработицы"], ["%"],
        ["Наименование региона", 2013, None, None, None, None, "20142)", None],
        [None, "I квартал", "II квартал", "III квартал", "IV квартал ", "год", "I квартал", "год"],
        ["Республика Казахстан", 5.3, 5.2, 5.2, 5.2, 5.2, 5.1, 5.0],
        ["Акмолинская ", 5.0, 5.0, 5.0, 5.0, 5.0, 5.0, 5.0],
    ])
    recs = bns.parse_labour_indicator_block(content, "Уровень безработицы")
    assert [r["date"] for r in recs] == ["2013-03-31", "2013-06-30", "2013-09-30", "2013-12-31", "2014-03-31"]
    assert recs[-1]["value"] == 5.1


def test_wage_1t_quarterly_pairs_of_label_and_value_rows():
    from fetchers import bns
    content = _xlsx("Показатель", [
        [None, "Январь", "Февраль"],
        [2014, 104654, 104949],
        [2015, "1 квартал", None, None, "2 квартал", None, None, "3 квартал", None, None, "4 квартал"],
        [None, 118638, None, None, 124227, None, None, 124656, None, None, 136094],
        [2026, "1 квартал", None, None, "2 квартал", None, None, "3 квартал"],
        [None, 461486, None, None, 486388, None, None, None],
    ])
    recs = bns.parse_wage_1t_quarterly(content)
    assert [(r["date"], r["value"]) for r in recs] == [
        ("2015-03-31", 118638.0), ("2015-06-30", 124227.0), ("2015-09-30", 124656.0), ("2015-12-31", 136094.0),
        ("2026-03-31", 461486.0), ("2026-06-30", 486388.0)]
