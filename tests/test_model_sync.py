import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import model_sync  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]


def _obs(pairs):
    return [model_sync.Observation(d, v, "bns", "2026-09-04") for d, v in pairs]


def test_annual_last_takes_the_last_observation_inside_the_year():
    obs = _obs([("2024-12-31", 10.0), ("2025-01-01", 20.0), ("2025-12-31", 30.0)])
    assert model_sync.annual_value(obs, 2025, "last") == 30.0
    assert model_sync.annual_value(obs, 2024, "last") == 10.0
    assert model_sync.annual_value(obs, 2023, "last") is None   # nothing fabricated for an absent year


def test_annual_mean_and_sum_use_only_that_year():
    obs = _obs([("2024-12-30", 100.0), ("2025-01-02", 500.0), ("2025-01-03", 520.0), ("2025-01-04", 540.0)])
    assert model_sync.annual_value(obs, 2025, "mean") == pytest.approx(520.0)
    assert model_sync.annual_value(obs, 2025, "sum") == pytest.approx(1560.0)


def test_annual_december_needs_a_december_observation():
    obs = _obs([("2025-11-01", 111.0), ("2025-12-01", 112.3)])
    assert model_sync.annual_value(obs, 2025, "december") == 112.3
    assert model_sync.annual_value(_obs([("2025-11-01", 111.0)]), 2025, "december") is None


def test_unknown_rule_is_an_error_not_a_default():
    with pytest.raises(ValueError):
        model_sync.annual_value(_obs([("2025-12-31", 1.0)]), 2025, "median")


def test_transform_scales_then_offsets():
    assert model_sync.transform(112.3, offset=-100.0) == pytest.approx(12.3)
    assert model_sync.transform(159_608_552_900_000.0, scale=1e-6) == pytest.approx(159_608_552.9)
    assert model_sync.transform(None, scale=1e-6) is None


def test_year_columns_reads_calendar_years_from_a_header_row():
    header = [None, "label", 2022, 2023.0, "2024", 2024, 2025, True]
    assert model_sync.year_columns(header, {2023, 2024, 2025}) == {2023: 4, 2024: 6, 2025: 7}


def test_check_status_never_marks_a_formula_cell_for_writing():
    common = dict(mapping_id="x", variable="X", sheet="S", cell="A1", year=2025, tolerance=0.5)
    assert model_sync.Check(model=1.0, pipeline=1.4, is_formula=False, **common).status == "ok"
    assert model_sync.Check(model=1.0, pipeline=2.0, is_formula=False, **common).status == "diff"
    assert model_sync.Check(model=1.0, pipeline=2.0, is_formula=True, **common).status == "control"
    assert model_sync.Check(model=None, pipeline=2.0, is_formula=False, **common).status == "diff"      # empty input: fillable
    assert model_sync.Check(model=None, pipeline=2.0, is_formula=True, **common).status == "control"
    assert model_sync.Check(model=0.0, pipeline=None, is_formula=False, **common).status == "missing"   # nothing to fill from
    # only an explicit, mapping-level decision lets a formula be replaced
    assert model_sync.Check(model=1.0, pipeline=2.0, is_formula=True, replace_formula=True, **common).status == "diff"
    assert model_sync.Check(model=2.0, pipeline=2.0, is_formula=True, replace_formula=True, **common).status == "ok"


def test_relative_tolerance_widens_the_absolute_one_never_narrows_it():
    common = dict(mapping_id="x", variable="X", sheet="S", cell="A1", year=2025, is_formula=False)
    # gold at $3 442: 1 % is $34 — a $20 difference is rounding, not a revision
    assert model_sync.Check(model=3422.0, pipeline=3442.0, tolerance=0.006, rel_tolerance=0.01, **common).status == "ok"
    assert model_sync.Check(model=3400.0, pipeline=3442.0, tolerance=0.006, rel_tolerance=0.01, **common).status == "diff"
    # tea at $2.91: 1 % is 3 cents, so the absolute floor of 0.006 still carries a 0.005 gap
    assert model_sync.Check(model=2.905, pipeline=2.91, tolerance=0.006, rel_tolerance=0.001, **common).status == "ok"
    assert model_sync.Check(model=2.8, pipeline=2.91, tolerance=0.006, rel_tolerance=0.01, **common).status == "diff"


def test_build_ops_marks_a_replaced_formula_in_comment_and_journal():
    checks = [model_sync.Check("a", "A", "S", "B2", 2025, 1.0, 2.0, True, 0.1, replace_formula=True)]
    ops = model_sync.build_ops(checks, {}, {"model": {"journal_sheet": "J"}}, journal_next_row=5, today="14.09.2026")
    assert any(o["op"] == "value" and o["cell"] == "B2" for o in ops)
    assert "по решению автора" in next(o["text"] for o in ops if o["op"] == "comment")
    assert "формула заменена фактом" in next(o for o in ops if o["op"] == "table")["rows"][1][4]


def test_build_ops_writes_only_diff_inputs_and_journals_them():
    checks = [
        model_sync.Check("a", "A", "S", "B2", 2025, 1.0, 2.0, False, 0.1),
        model_sync.Check("b", "B", "S", "B3", 2025, 1.0, 2.0, True, 0.1),    # control: must not be written
        model_sync.Check("c", "C", "S", "B4", 2025, 2.0, 2.0, False, 0.1),   # ok
    ]
    series = {"A": [model_sync.Observation("2025-12-31", 2.0, "bns", "2026-09-04")]}
    cfg = {"model": {"journal_sheet": "J"}}
    ops = model_sync.build_ops(checks, series, cfg, journal_next_row=10, today="14.09.2026")
    kinds = [(o["op"], o.get("cell")) for o in ops]
    assert ("value", "B2") in kinds and ("comment", "B2") in kinds
    assert not any(o.get("cell") in ("B3", "B4") for o in ops if o["op"] == "value")
    table = next(o for o in ops if o["op"] == "table")
    assert table["sheet"] == "J" and table["cell"] == "A10" and len(table["rows"]) == 2   # header + one change


def test_model_map_is_well_formed_and_names_real_pipeline_variables():
    cfg = yaml.safe_load((REPO_ROOT / "config" / "model_map.yaml").read_text(encoding="utf-8"))
    indicators = yaml.safe_load((REPO_ROOT / "config" / "indicators.yaml").read_text(encoding="utf-8"))["indicators"]
    dims_cfg = yaml.safe_load((REPO_ROOT / "config" / "dims.yaml").read_text(encoding="utf-8"))["datasets"]
    known, known_dims = {i["id"] for i in indicators}, {d["id"] for d in dims_cfg}
    ids = [m["id"] for m in cfg["mappings"]]
    assert len(ids) == len(set(ids)), "mapping ids must be unique"
    for m in cfg["mappings"]:
        assert m.get("annual", "last") in model_sync.ANNUAL_RULES
        if "dims_variable" in m:
            assert m["dims_variable"] in known_dims, f"{m['id']}: {m['dims_variable']} is not in dims.yaml"
            assert m["sheet"] and (m.get("rows_by_item") or m.get("item_column") or m.get("blocks")), f"{m['id']} has no rows"
            for code, row in m.get("rows_by_item", {}).items():
                assert int(row) > 0, f"{m['id']}[{code}]"
            if m.get("blocks"):
                assert m.get("region_column"), f"{m['id']}: blocks need a region_column"
                for code, (first, last) in m["blocks"].items():
                    assert 0 < int(first) <= int(last), f"{m['id']}[{code}]"
        else:
            assert m["variable"] in known, f"{m['id']}: {m['variable']} is not in indicators.yaml"
            assert m["targets"], f"{m['id']} has no targets"
            for t in m["targets"]:
                assert t["sheet"] and int(t["row"]) > 0


def test_item_rows_reads_codes_from_a_sheet_column_with_aliases():
    column = [None, "A", "B", 5, 6.0, "ЧН", "ВДС", "A"]      # numbers are two-digit division codes; first hit wins
    rows = model_sync.item_rows(column, first_row=7, aliases={"NET_TAXES": "ЧН", "GVA": "ВДС"})
    assert rows == {"A": 8, "B": 9, "05": 10, "06": 11, "NET_TAXES": 12, "GVA": 13}


def test_load_unified_dims_keys_on_variable_item_and_region(tmp_path):
    p = tmp_path / "dims.csv"
    p.write_text("date,country,region,frequency,variable,item_code,item_name,value,unit,source,source_version,transformation,last_updated\n"
                 "2024-12-31,KZ,national,annual,X,A,a,1.5,u,bns,,level,2026-09-14\n"
                 "2024-12-31,KZ,AKM,annual,X,A,a,0.2,u,bns,,level,2026-09-14\n"
                 "2025-12-31,KZ,national,annual,X,A,a,n/a,u,bns,,level,2026-09-14\n", encoding="utf-8")
    series = model_sync.load_unified_dims(p)
    assert [(o.date, o.value) for o in series[("X", "A", "national")]] == [("2024-12-31", 1.5)]
    assert [o.value for o in series[("X", "A", "AKM")]] == [0.2]
    assert model_sync.load_unified_dims(tmp_path / "absent.csv") == {}


def test_region_rows_reads_region_names_as_the_model_spells_them():
    column = ["Среднегодовая численность населения", "Абай", "З-Казахстанская ", "Жетісу", "Туркестанская*", "г. Астана", "г.Шымкент3)", "Абай"]
    rows = model_sync.region_rows(column, first_row=164)
    assert rows == {"ABY": 165, "ZKO": 166, "ZHT": 167, "TRK": 168, "AST": 169, "SHM": 170}
