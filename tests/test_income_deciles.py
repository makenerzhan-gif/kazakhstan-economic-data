"""Income by decile (fetchers/bns_living.py, 2026-09-25)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from fetchers import bns_living  # noqa: E402


def test_edition_period_from_the_cover():
    assert bns_living.edition_period([[None, "Дата опубликования: 28.04.2026"], ["2025 год"]]) == ("annual", 2025, 12)
    assert bns_living.edition_period([["за 2022 год"]]) == ("annual", 2022, 12)
    assert bns_living.edition_period([["I квартал 2026 года"]]) == ("quarterly", 2026, 1)
    assert bns_living.edition_period([["IV квартал 2025 года"]]) == ("quarterly", 2025, 4)


def test_decile_table_both_layouts():
    header = ["Децили", "Границы интервалов по доходу населения, тенге", "Доля дохода в интервале, в процентах",
              "Среднемесячный доход на душу населения в интервале, тенге"]
    rows = [["6. Распределение доходов по 10-процентным группам населения"], header,
            ["1", "0-54 440", "4.09", "44360"]] + [[str(i), f"{i}0-{i}9", "10", "1"] for i in range(2, 11)] + [["Итого", None, "100"]]
    got = bns_living.parse_decile_table(rows)
    assert len(got) == 10 and got["D01"] == {"share": 4.09, "mean": 44360.0, "lower": 0.0, "upper": 54440.0}
    # the 2022 edition: an empty column between the decile number and the bounds
    shifted = [[r[0], None] + r[1:] if isinstance(r, list) and len(r) > 1 else r for r in rows]
    assert bns_living.parse_decile_table(shifted)["D01"]["upper"] == 54440.0


def test_poverty_table_national_row_in_kazakh_or_russian():
    head = [None, "Глубина бедности, в процентах", "Острота бедности, в процентах", "Коэффициент Джини, по 10% группам",
            "Коэффициент Джини, по 20% группам", "Соотношение 10% наиболее и 10% наименее"]
    for label in ("Қазақстан Республикасы ", "Республика Казахстан"):
        got = bns_living.parse_poverty_table([["5. Основные показатели бедности"], head,
                                              [label, "0.9", "0.2", "0.283", "0.269", "5.66"], ["Абай", 1, 1, 1, 1, 1]])
        assert got == {"depth": 0.9, "severity": 0.2, "gini10": 0.283, "gini20": 0.269, "ratio": 5.66}


def test_taldau_quarter_keys_become_quarter_starts():
    node = {"y032011": "4.2", "y122024": "3.91", "id": "742657"}
    assert bns_living.taldau_values(node, "quarterly") == {"2011-01-01": 4.2, "2024-10-01": 3.91}
    assert bns_living.taldau_values({"y122024": "4.03"}, "annual") == {"2024-12-31": 4.03}
