"""IMF BOP/IIP/GFS and WDI-for-Kazakhstan item-level datasets (fetchers/imf_dims.py,
gravity.fetch_wdi_country): the SDMX parsing on synthetic answers, the weekly refresh gate,
and the stored data against NBK's and the WEO's own series."""
import csv
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from fetchers import imf_dims  # noqa: E402
from lib import dims, raw_store  # noqa: E402

DIMS = REPO_ROOT / "data" / "processed" / "dims"


@pytest.mark.parametrize("period,freq,kind,expected", [
    ("2025", "annual", "flow", "2025-12-31"),
    ("2025-Q3", "quarterly", "flow", "2025-07-01"),
    ("2025-Q3", "quarterly", "stock", "2025-09-30"),
    ("2025-Q4", "quarterly", "stock", "2025-12-31"),
    ("2025-M03", "quarterly", "flow", None),
    ("2025-Q1", "annual", "flow", None),
])
def test_period_date(period, freq, kind, expected):
    assert imf_dims.period_date(period, freq, kind) == expected


STRUCTURE = {"data": {
    "conceptSchemes": [{"agencyID": "IMF.STA", "id": "CS_BOP", "concepts": [
        {"id": "INDICATOR", "coreRepresentation": {"enumeration": "urn:sdmx:org.sdmx.infomodel.codelist.Codelist=IMF.STA:CL_BOP_INDICATOR(10.0+.0)"}}]}],
    "codelists": [{"agencyID": "IMF.STA", "id": "CL_BOP_INDICATOR", "codes": [{"id": "CAB", "name": "Current account balance"}]},
                  {"agencyID": "IMF.STA", "id": "CL_ENTRY", "codes": [{"id": "NETCD_T", "name": "Net (credits less debits)"}]}],
    "dataStructures": [{"dataStructureComponents": {"dimensionList": {"dimensions": [
        {"id": "INDICATOR", "conceptIdentity": "urn:sdmx:org.sdmx.infomodel.conceptscheme.Concept=IMF.STA:CS_BOP(17.0+.0).INDICATOR"},
        {"id": "BOP_ACCOUNTING_ENTRY", "localRepresentation": {"enumeration": "urn:sdmx:org.sdmx.infomodel.codelist.Codelist=IMF.STA:CL_ENTRY(1.0)"}},
    ]}}}]}}

CSV = (
    "COUNTRY,BOP_ACCOUNTING_ENTRY,INDICATOR,UNIT,FREQUENCY,TIME_PERIOD,OBS_VALUE\n"
    "KAZ,NETCD_T,CAB,USD,Q,2025-Q4,-5180443517\n"
    "KAZ,NETCD_T,CAB,USD,Q,2026-Q1,\n"                      # blank: skipped
    "KAZ,NETCD_T,CAB,USD,A,2025,-12000000000\n"             # other frequency: skipped
    "KAZ,NETCD_T,XYZ,USD,Q,2025-Q4,1500000\n"               # a code the codelist lacks: named by the code
).encode()


def test_dimension_names_follow_concept_and_local_representation():
    names = imf_dims.dimension_names(STRUCTURE)
    assert names["INDICATOR"]["CAB"] == "Current account balance"
    assert names["BOP_ACCOUNTING_ENTRY"]["NETCD_T"] == "Net (credits less debits)"


def test_parse_scales_names_and_dates():
    ds = {"id": "T", "frequency": "quarterly", "period": "flow", "divisor": 1_000_000,
          "code_dims": ["BOP_ACCOUNTING_ENTRY", "INDICATOR"]}
    recs = imf_dims.parse(CSV, ds, imf_dims.dimension_names(STRUCTURE))
    assert [(r["date"], r["item_code"], r["value"]) for r in recs] == [
        ("2025-10-01", "NETCD_T.CAB", -5180.443517), ("2025-10-01", "NETCD_T.XYZ", 1.5)]
    assert recs[0]["item_name"] == "Net (credits less debits) | Current account balance"
    assert recs[1]["item_name"].endswith("| XYZ")


def test_parse_refuses_codes_that_do_not_identify_a_series():
    ds = {"id": "T", "frequency": "quarterly", "code_dims": ["BOP_ACCOUNTING_ENTRY"]}
    with pytest.raises(ValueError, match="do not identify"):
        imf_dims.parse(CSV, ds, {})


def test_refresh_gate(tmp_path, monkeypatch):
    monkeypatch.setattr(raw_store, "RAW_ROOT", tmp_path / "raw")
    monkeypatch.setattr(dims, "PROCESSED_ROOT", tmp_path / "dims")
    ds = {"id": "IMF_T", "frequency": "annual"}
    assert imf_dims.stored_if_fresh(ds, "imf", "IMF_T") is None                 # nothing stored yet
    dims.write_processed("IMF_T", [{"date": "2025-12-31", "region": "national", "item_code": "A", "item_name": "a", "value": 1.0}])
    folder = tmp_path / "raw" / "imf"
    folder.mkdir(parents=True)
    (folder / f"imf_imf_t_{(date.today() - timedelta(days=2)).isoformat()}.manifest.json").write_text("{}")
    recs, manifest = imf_dims.stored_if_fresh(ds, "imf", "IMF_T")
    assert recs[0]["value"] == 1.0 and "not re-downloaded" in manifest["warnings"][0]
    assert imf_dims.stored_if_fresh({**ds, "refresh_days": 2}, "imf", "IMF_T") is None
    assert imf_dims.stored_if_fresh({**ds, "refresh_days": 0}, "imf", "IMF_T") is None


# ---------------------------------------------------------------- the stored data

def _item(dataset, code):
    with (DIMS / f"{dataset.lower()}.csv").open(encoding="utf-8") as f:
        return {r["date"]: float(r["value"]) for r in csv.DictReader(f) if r["item_code"] == code}


def _scalar(agency, indicator):
    with (REPO_ROOT / "data" / "processed" / agency / f"{indicator.lower()}.csv").open(encoding="utf-8") as f:
        return {r["date"]: float(r["value"]) for r in csv.DictReader(f) if r["value"]}


def test_imf_current_account_is_nbks():
    """Same quarters, same dates (quarter start). 2023Q1-2025Q2 differ by 14-350 mn: NBK has revised them
    and the IMF's BOP does not carry the revision yet — NBK stays the primary source."""
    imf, nbk = _item("IMF_BOP_QUARTERLY", "NETCD_T.CAB"), _scalar("nbk", "CURRENT_ACCOUNT_BALANCE")
    common = sorted(set(imf) & set(nbk))
    same = [d for d in common if abs(imf[d] - nbk[d]) < 1.0]
    assert len(common) >= 100 and len(same) >= 0.85 * len(common)
    assert all(d in same for d in common[-2:])


def test_imf_net_iip_is_nbks_one_day_earlier():
    imf, nbk = _item("IMF_IIP_QUARTERLY", "NETAL_P.NIIP"), _scalar("nbk", "IIP_NET")
    shifted = {(date.fromisoformat(d) + timedelta(days=1)).isoformat(): v for d, v in imf.items()}
    common = set(shifted) & set(nbk)
    assert len(common) >= 20 and all(abs(shifted[d] - nbk[d]) < 1.0 for d in common)


def test_wdi_gdp_equals_the_weo_outturns():
    wdi, weo = _item("WDI_KAZ", "NY.GDP.MKTP.CN"), _scalar("imf", "IMF_NOMINAL_GDP")
    years = [d for d in set(wdi) & set(weo) if "1994-12-31" <= d <= "2024-12-31"]
    assert len(years) >= 30 and all(abs(wdi[d] / weo[d] - 1) < 0.001 for d in years)


def test_gfs_general_government_balance_is_revenue_less_expenditure():
    rev, exp_, bal = (_item("IMF_GFS_OPERATIONS_KZT", f"S13.{c}") for c in ("G1_T", "G2_T", "GNLB_T"))
    nfa = _item("IMF_GFS_OPERATIONS_KZT", "S13.G31_A_T")
    years = [d for d in rev if d in exp_ and d in bal and d in nfa and d >= "2010-12-31"]
    assert len(years) >= 10
    assert all(abs(rev[d] - exp_[d] - nfa[d] - bal[d]) < 0.01 * rev[d] for d in years)
