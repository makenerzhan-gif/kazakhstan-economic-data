"""NBK paginated form downloads are archived in canonical form (lib/nbk_pages): the same
data served with rows in another order or spread differently over the pages, or with the
per-page column labels the API varies at random (formId=132, 2026-08-31..09-26), must give
the same bytes -- so raw_store stores it once -- while every row and value is kept."""
import json
import random
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import dedup_raw  # noqa: E402
from fetchers import nbk  # noqa: E402
from lib import nbk_pages, raw_store  # noqa: E402

COLUMNS = [{"key": "report_date", "label": "Report date", "colId": None},
           {"key": "amount", "label": "Amount", "colId": None},
           {"key": "residency", "label": "residency", "colId": None}]
ROWS = [{"report_date": f"2026-0{m}-01", "amount": float(m * 10 + k), "type": "thsd. tenge", "row_code": str(k),
         "insurance_org_type": "General", **({"residency": "Resident"} if k % 2 else {})}
        for m in range(1, 7) for k in range(1, 6)]
ROWS.append(dict(ROWS[3]))                                   # the API may serve a row twice: both are kept


def _pages(rows: list[dict], page_size: int, seed: int) -> list[dict]:
    """The rows as the API pages them, with the `residency` label varying page by page
    ("residency" / "Residency of institutional units"), as formId=132 does."""
    rng = random.Random(seed)
    pages = []
    for i in range(0, len(rows), page_size):
        label = rng.choice(["residency", "Residency of institutional units"])
        columns = [dict(c, label=label) if c["key"] == "residency" else dict(c) for c in COLUMNS]
        rng.shuffle(columns)
        pages.append({"locale": "en", "formId": 132, "columns": columns, "rows": [dict(r) for r in rows[i:i + page_size]],
                      "page": i // page_size, "pageSize": page_size, "totalRows": len(rows),
                      "filterReportDate": None, "filterStartDate": None, "filterEndDate": None})
    # both label variants on some page in every call, as observed (the union is what is kept)
    pages[0]["columns"] = [dict(c, label="residency") if c["key"] == "residency" else c for c in pages[0]["columns"]]
    pages[-1]["columns"] = [dict(c, label="Residency of institutional units") if c["key"] == "residency" else c
                            for c in pages[-1]["columns"]]
    return pages


def _shuffled(seed: int) -> list[dict]:
    rows = [dict(r) for r in ROWS]
    random.Random(seed).shuffle(rows)
    return rows


def test_shuffled_rows_and_varying_labels_give_identical_bytes():
    a = nbk_pages.canonical_form_bytes(_pages(ROWS, 7, seed=1))
    b = nbk_pages.canonical_form_bytes(_pages(_shuffled(2), 7, seed=3))
    assert a == b


def test_canonical_form_keeps_every_row_and_value():
    pages = _pages(_shuffled(5), 7, seed=5)
    doc = json.loads(nbk_pages.canonical_form_bytes(pages))
    served = sorted(json.dumps(r, sort_keys=True) for p in pages for r in p["rows"])
    assert sorted(json.dumps(r, sort_keys=True) for r in doc["rows"]) == served
    assert len(doc["rows"]) == len(ROWS)                               # the repeated row is not collapsed
    assert [r["report_date"] for r in doc["rows"]] == sorted(r["report_date"] for r in ROWS)
    assert doc["formId"] == 132 and doc["totalRows"] == len(ROWS) and doc["n_pages"] == len(pages)
    assert {c["label"] for c in doc["columns"] if c["key"] == "residency"} == {"residency", "Residency of institutional units"}
    assert doc["format"] == nbk_pages.CANONICAL_FORMAT and "envelope_varying" not in doc


def test_different_data_still_gives_different_bytes():
    changed = [dict(r) for r in ROWS]
    changed[0]["amount"] += 1
    assert nbk_pages.canonical_form_bytes(_pages(ROWS, 7, 1)) != nbk_pages.canonical_form_bytes(_pages(changed, 7, 1))


@pytest.fixture
def raw_root(tmp_path, monkeypatch):
    monkeypatch.setattr(raw_store, "RAW_ROOT", tmp_path)
    monkeypatch.setattr(dedup_raw, "RAW", tmp_path)
    monkeypatch.setattr(dedup_raw, "REPO_ROOT", tmp_path.parent)
    return tmp_path


def _serve(monkeypatch, pages: list[dict]) -> None:
    by_page = {str(p["page"]): p for p in pages}

    class Resp:
        def __init__(self, data):
            self._data = data

        def raise_for_status(self):
            pass

        def json(self):
            return json.loads(json.dumps(self._data))

    monkeypatch.setattr(nbk.requests, "get", lambda url, headers, params, timeout: Resp(by_page[params["page"]]))
    nbk._FORM_PAGES_CACHE.clear()                            # a new run: a new process has an empty cache


def test_a_second_run_with_the_same_data_stores_no_new_file(raw_root, monkeypatch):
    _serve(monkeypatch, _pages(ROWS, 7, seed=1))
    first_rows = nbk._fetch_nbk_form_paginated("132", "INSURANCE_PREMIUMS_GENERAL")
    _serve(monkeypatch, _pages(_shuffled(9), 7, seed=4))   # same data, other order and labels
    nbk._fetch_nbk_form_paginated("132", "INSURANCE_PREMIUMS_GENERAL")
    files = sorted(p.name for p in (raw_root / "nbk").glob("*.json") if not p.name.endswith(".manifest.json"))
    today = date.today().isoformat()
    assert files == [f"nbk_insurance_premiums_general_{today}.json"]
    assert len(first_rows) == len(ROWS)
    manifest = json.loads((raw_root / "nbk" / f"nbk_insurance_premiums_general_{today}.manifest.json").read_text(encoding="utf-8"))
    assert manifest["raw_file"] == files[0]
    assert manifest["raw_format"] == nbk_pages.CANONICAL_FORMAT and manifest["raw_normalisation"]
    assert manifest["rows_archived"] == len(ROWS)


def test_bop_history_form_gets_its_own_raw_file_and_manifest(raw_root, monkeypatch):
    """A BoP series reads 324 and, for the quarters before 2020, 481; each download keeps
    its own dated manifest (481 used to overwrite 324's) and neither is a "revision"."""
    def form(form_id: int, amount: float) -> list[dict]:
        rows = [{"report_date": "2020-01-01", "amount": amount, "code": "Goods", "row_id": "1"}]
        return [{"locale": "en", "formId": form_id, "columns": COLUMNS, "rows": rows, "page": 0,
                 "pageSize": 500, "totalRows": 1}]

    served = {"324": form(324, 1.0), "481": form(481, 2.0)}

    class Resp:
        def __init__(self, data):
            self._data = data

        def raise_for_status(self):
            pass

        def json(self):
            return json.loads(json.dumps(self._data))

    monkeypatch.setattr(nbk.requests, "get", lambda url, headers, params, timeout: Resp(served[params["formId"]][0]))
    nbk._FORM_PAGES_CACHE.clear()
    nbk._fetch_nbk_form_paginated(nbk.BOP_FORM_ID, "BOP_GOODS_BALANCE")
    nbk._bop_history("GOODS", "BOP_GOODS_BALANCE", {"2020-01-01": 1.0})
    today = date.today().isoformat()
    folder = raw_root / "nbk"
    assert sorted(p.name for p in folder.glob("*.json") if not p.name.endswith(".manifest.json")) == [
        f"nbk_bop_goods_balance_{today}.json", f"nbk_bop_goods_balance_history_{today}.json"]
    for stem, form_id in (("bop_goods_balance", "324"), ("bop_goods_balance_history", "481")):
        manifest = json.loads((folder / f"nbk_{stem}_{today}.manifest.json").read_text(encoding="utf-8"))
        assert manifest["form_id"] == form_id and manifest["raw_file"] == f"nbk_{stem}_{today}.json"


def test_dedup_nbk_forms_removes_copies_equal_in_canonical_form(raw_root):
    folder = raw_root / "nbk"
    folder.mkdir()
    old = [("nbk_insurance_premiums_general_2026-09-24.json", _pages(ROWS, 7, 1)),
           ("nbk_insurance_premiums_general_2026-09-26.json", _pages(_shuffled(2), 7, 2)),
           ("nbk_bop_goods_balance_2026-09-25.json", _pages(_shuffled(3), 7, 3))]
    for name, pages in old:
        (folder / name).write_bytes(json.dumps(pages, ensure_ascii=False).encode("utf-8"))
    canonical = "nbk_insurance_premiums_general_2026-09-26_120000.json"
    (folder / canonical).write_bytes(nbk_pages.canonical_form_bytes(_pages(ROWS, 7, 4)))
    changed = [dict(r, amount=r["amount"] + 1) for r in ROWS]
    (folder / "nbk_insurance_premiums_general_2026-09-10.json").write_bytes(json.dumps(_pages(changed, 7, 1)).encode())
    (folder / "nbk_money_records_2026-09-24.json").write_bytes(b'[{"a": 1}]')        # not a form download
    m = folder / "nbk_insurance_premiums_general_2026-09-24.manifest.json"
    m.write_text(json.dumps({"downloaded_at": "2026-09-24T06:00:00"}), encoding="utf-8")   # old manifests: no raw_file
    m2 = folder / "nbk_bop_goods_balance_2026-09-25.manifest.json"
    m2.write_text(json.dumps({"raw_file": "nbk_bop_goods_balance_2026-09-25.json"}), encoding="utf-8")

    assert dedup_raw.main(["--nbk-forms"]) == 0
    left = sorted(p.name for p in folder.glob("*.json") if not p.name.endswith(".manifest.json"))
    assert left == ["nbk_insurance_premiums_general_2026-09-10.json", canonical, "nbk_money_records_2026-09-24.json"]
    assert json.loads(m2.read_text(encoding="utf-8"))["raw_file"] == canonical
    assert json.loads(m.read_text(encoding="utf-8"))["raw_file"] == canonical      # named its file by its own stem
    assert "canonical form" in json.loads(m2.read_text(encoding="utf-8"))["raw_file_note"]
    record = json.loads(next(raw_root.glob("dedup_*.json")).read_text(encoding="utf-8"))
    rel = raw_root.name + "/nbk/"
    assert set(record["nbk_forms_removed"]) == {rel + name for name, _ in old}
    assert all(record["removed"][rel + name] == rel + canonical for name, _ in old)
    assert record["nbk_forms_rule"]


def test_dedup_wits_removes_answers_equal_apart_from_the_stamp(raw_root):
    folder = raw_root / "wits"
    folder.mkdir()

    def answer(prepared, value=1.0):
        return json.dumps({"header": {"id": "x", "prepared": prepared}, "dataSets": [{"v": value}]}).encode()

    (folder / "wits_exports_2026-09-25.json").write_bytes(answer("2026-09-25T14:53:30"))
    (folder / "wits_exports_2026-09-26.json").write_bytes(answer("2026-09-26T01:54:18"))
    (folder / "wits_exports_2026-09-26_082354.json").write_bytes(answer("2026-09-26T08:23:54"))
    (folder / "wits_exports_2026-09-27.json").write_bytes(answer("2026-09-27T01:00:00", 2.0))     # new data
    m = folder / "wits_exports_2026-09-26.manifest.json"
    m.write_text(json.dumps({"raw_file": "wits_exports_2026-09-26_082354.json"}), encoding="utf-8")

    assert dedup_raw.main(["--wits"]) == 0
    assert sorted(p.name for p in folder.glob("*.json") if not p.name.endswith(".manifest.json")) == [
        "wits_exports_2026-09-25.json", "wits_exports_2026-09-27.json"]
    info = json.loads(m.read_text(encoding="utf-8"))
    assert info["raw_file"] == "wits_exports_2026-09-25.json" and "header.prepared" in info["raw_file_note"]
    record = json.loads(next(raw_root.glob("dedup_*.json")).read_text(encoding="utf-8"))
    assert len(record["wits_removed"]) == 2 and record["wits_rule"]
