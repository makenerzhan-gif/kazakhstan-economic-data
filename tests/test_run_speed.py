"""Run-time fixes of 2026-11-13: the Minfin workbook cache and the per-host circuit breaker."""
import io
import sys
from pathlib import Path

import openpyxl
import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from fetchers import gravity, minfin  # noqa: E402


def _xlsx() -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "табл 1"
    ws.append(["a", 1, None])
    ws.append([None, 2.5, "b"])
    wb.create_sheet("табл 2").append(["x"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_workbook_is_parsed_once_and_rows_are_copies(monkeypatch):
    content = _xlsx()
    minfin._WORKBOOK_CACHE.clear()
    calls = []
    real = openpyxl.load_workbook
    monkeypatch.setattr(minfin.openpyxl, "load_workbook", lambda *a, **k: (calls.append(1), real(*a, **k))[1])
    kind, wb = minfin._open_workbook(content, "bulletin.xlsx")
    kind2, wb2 = minfin._open_workbook(content, "another-name.xlsx")
    assert kind == kind2 == "openpyxl" and wb is wb2 and len(calls) == 1
    assert wb.sheetnames == ["табл 1", "табл 2"] == wb.sheet_names()
    rows = list(minfin._iter_rows(kind, wb, "табл 1"))
    assert rows == [["a", 1, None], [None, 2.5, "b"]] and list(minfin._iter_rows(kind, wb)) == rows
    rows[0][0] = "edited"                                   # a caller's edit must not reach the cache
    assert list(minfin._iter_rows(kind, wb, "табл 1"))[0][0] == "a"


class _Resp:
    def __init__(self, status, content=b"ok"):
        self.status_code, self.content = status, content

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}")


def test_host_is_not_asked_again_after_a_timeout_or_5xx(monkeypatch):
    gravity._CACHE.clear()
    gravity._HOST_DOWN.clear()
    calls = []

    def fake_get(url, headers=None, timeout=None):
        calls.append(url)
        if "slow.example" in url:
            raise requests.ReadTimeout("read timed out")
        if "bad.example" in url:
            return _Resp(502)
        if "missing" in url:
            return _Resp(404)
        return _Resp(200)

    monkeypatch.setattr(gravity.requests, "get", fake_get)
    with pytest.raises(requests.ReadTimeout):
        gravity._get("https://slow.example/a")
    with pytest.raises(gravity.HostDownError, match="slow.example"):
        gravity._get("https://slow.example/b")
    with pytest.raises(requests.HTTPError):
        gravity._get("https://bad.example/a")
    with pytest.raises(gravity.HostDownError):
        gravity._get("https://bad.example/b")
    with pytest.raises(requests.HTTPError):                # a 404 is the request's fault: the host stays up
        gravity._get("https://good.example/missing")
    assert gravity._get("https://good.example/x") == b"ok"
    assert calls == ["https://slow.example/a", "https://bad.example/a", "https://good.example/missing", "https://good.example/x"]
    gravity._HOST_DOWN.clear()


def test_wdi_is_not_downloaded_again_within_a_month(monkeypatch):
    from fetchers import imf_dims
    seen = {}
    monkeypatch.setattr(imf_dims, "stored_if_fresh", lambda ds, agency, name: (seen.update(ds=ds, key=(agency, name)), ("recs", {}))[1])
    monkeypatch.setattr(gravity, "_get", lambda *a, **k: pytest.fail("downloaded although fresh"))
    assert gravity.fetch_wdi({"id": "WGI_GE", "indicator": "X", "frequency": "annual"}) == ("recs", {})
    assert seen["ds"]["refresh_days"] == 30 and seen["key"] == ("wb", "WGI_GE")
    gravity.fetch_wdi({"id": "WGI_GE", "indicator": "X", "frequency": "annual", "refresh_days": 7})
    assert seen["ds"]["refresh_days"] == 7                  # the dataset's own setting wins


# ---------------------------------------------------------------- parallel updaters, stale series

def _fake_updater(tmp_path, name, source, n, delay=0.0):
    (tmp_path / f"{name}.py").write_text(
        "import time\nfrom lib import pipeline_logging\n"
        f"def run(logger):\n    time.sleep({delay})\n    for i in range({n}):\n"
        f"        logger.log(pipeline_logging.LogEntry(timestamp=str(i), source='{source}', dataset=f'D{{i}}', action='fetch', status='ok'))\n",
        encoding="utf-8")


def test_run_parallel_keeps_group_order_and_leaves_one_log(tmp_path, monkeypatch):
    import update_all
    from lib import pipeline_logging
    monkeypatch.setattr(pipeline_logging, "LOGS_ROOT", tmp_path / "logs")
    monkeypatch.syspath_prepend(str(tmp_path))
    _fake_updater(tmp_path, "fake_a", "a", 2, delay=0.3)      # the slow group still comes first in the log
    _fake_updater(tmp_path, "fake_b", "b", 1)
    _fake_updater(tmp_path, "fake_c", "c", 1)
    logger = pipeline_logging.RunLogger(run_timestamp="2026-01-01T00:00:00")
    update_all.run_parallel((("fake_a",), ("fake_b", "fake_c")), logger)
    assert [(e.source, e.dataset) for e in logger.entries] == [("a", "D0"), ("a", "D1"), ("b", "D0"), ("c", "D0")]
    assert [p.name for p in (tmp_path / "logs").iterdir()] == [logger.path.name]      # no part files left
    assert len(logger.path.read_text(encoding="utf-8").splitlines()) == 4

    serial = pipeline_logging.RunLogger(run_timestamp="2026-01-01T00:00:01")
    monkeypatch.setenv("UPDATE_ALL_SERIAL", "1")
    update_all.run_parallel((("fake_a",), ("fake_b", "fake_c")), serial)
    assert [(e.source, e.dataset) for e in serial.entries] == [(e.source, e.dataset) for e in logger.entries]


def test_run_parallel_groups_cover_the_scalar_updaters_once():
    import update_all
    names = [n for g in update_all.PARALLEL_GROUPS for n in g]
    assert sorted(names) == sorted(["update_bns", "update_nbk", "update_minfin", "update_imf", "update_ardfm", "update_wb", "update_kase"])
    assert "update_foreign" not in names and "update_dims" not in names      # they read the others' files


def test_stale_series(tmp_path):
    from datetime import date
    from lib import staleness
    (tmp_path / "x").mkdir()
    for name, last in (("fresh_m", "2026-09-01"), ("old_m", "2026-04-01"), ("old_q", "2024-04-01"), ("old_ok", "2020-01-01"),
                       ("proj", "2020-12-31"), ("annual_fine", "2024-12-31")):
        (tmp_path / "x" / f"{name}.csv").write_text(f"date,value,transformation\n2019-01-01,1,level\n{last},2,level\n", encoding="utf-8")
    inds = [{"id": "FRESH_M", "agency": "x", "frequency": "monthly"}, {"id": "OLD_M", "agency": "x", "frequency": "monthly"},
            {"id": "OLD_Q", "agency": "x", "frequency": "quarterly"},
            {"id": "OLD_OK", "agency": "x", "frequency": "monthly", "stale_ok": "discontinued by the source in 2020"},
            {"id": "PROJ", "agency": "x", "frequency": "annual", "category": "international_projection"},
            {"id": "ANNUAL_FINE", "agency": "x", "frequency": "annual"}, {"id": "NO_FILE", "agency": "x", "frequency": "monthly"},
            {"id": "IRREGULAR", "agency": "x", "frequency": "irregular"}]
    stale = staleness.stale_series(inds, today=date(2026, 11, 13), processed_root=tmp_path)
    assert [r["id"] for r in stale] == ["OLD_OK", "OLD_Q", "OLD_M"] and stale[2]["days"] == 226
    assert [r["id"] for r in staleness.unexplained(stale)] == ["OLD_Q", "OLD_M"]          # the explained one raises no warning
    lines = staleness.report_lines(stale)
    assert any("x/OLD_M" in line for line in lines) and any("discontinued by the source" in line for line in lines)
    assert staleness.report_lines([]) == []
    life = staleness.stale_series([{"id": "OLD_Q", "agency": "x", "frequency": "quarterly", "lifecycle": "superseded", "superseded_by": "NEW"}],
                                  today=date(2026, 11, 13), processed_root=tmp_path)
    assert life[0]["known"] == "superseded, see NEW" and staleness.unexplained(life) == []


def test_bulletin_title_is_matched_whatever_its_capitals():
    assert minfin._is_bulletin_title("Statistical Bulletin as of oktober 1, 2026")        # the edition of 2026-11-05
    assert minfin._is_bulletin_title("Statistical bulletin as of September 1, 2026")
    assert not minfin._is_bulletin_title("State and State Guaranteed Debt") and not minfin._is_bulletin_title(None)


def test_every_stale_series_in_the_repository_is_explained():
    import yaml
    from lib import staleness
    inds = yaml.safe_load((Path(__file__).resolve().parents[1] / "config" / "indicators.yaml").read_text(encoding="utf-8"))["indicators"]
    for ind in inds:
        assert not (ind.get("stale_ok") and ind.get("lifecycle")), ind["id"]            # one explanation, not two
        assert ind.get("stale_ok") is None or len(str(ind["stale_ok"])) > 40, ind["id"]   # a reason, not a flag


# ---------------------------------------------------------------- the run's issue, model_data in the run

def test_run_issue_body():
    import run_issue
    report = ("# Update report\n\n## Cross-source checks that failed (they never block the commit)\n\ntext\n\n- `tests/a.py::t - x`\n\n"
              "## Failed this run — previous data kept\n\n- **wb/WGI_GE**: 502\n- **wb/WGI_CC**: 502\n\n"
              "## Series with no new observations for longer than their frequency allows\n\nwhy\n\n- **nbk/NPL_RATIO** (quarterly): last\n\n"
              "## Per-dataset results\n\n- **bns/CPI** — fetch: ok\n")
    body = run_issue.body(report, "success", "http://run")
    assert "Не загрузились (сохранены прежние данные): 2" in body and "wb/WGI_CC" in body and "nbk/NPL_RATIO" in body
    assert "bns/CPI" not in body and "не закоммичены" not in body
    clean = "# Update report\n\n## Series with no new observations\n\n- **nbk/NPL_RATIO**\n\n## Per-dataset results\n\n- x\n"
    assert run_issue.body(clean, "success", "u") is None                # stale series alone open no issue
    assert "не закоммичены" in run_issue.body(clean, "failure", "u")
    assert "Отчёт не был записан" in run_issue.body(None, "failure", "u")
    assert "model_data" in run_issue.body("## model_data not rebuilt — previous panel kept\n\n- X13Error: boom\n", "success", "u")


def test_model_data_failure_restores_the_previous_panel(tmp_path, monkeypatch):
    import types
    import update_all
    folder = tmp_path / "model_data"
    folder.mkdir()
    (folder / "monthly.csv").write_text("old", encoding="utf-8")
    monkeypatch.setattr(update_all, "REPO_ROOT", tmp_path)

    def broken():
        (folder / "monthly.csv").write_text("half-written", encoding="utf-8")
        raise RuntimeError("x13 failed")
    monkeypatch.setitem(sys.modules, "build_model_data", types.SimpleNamespace(main=broken))
    reason = update_all.build_model_data_safely()
    assert "x13 failed" in reason and (folder / "monthly.csv").read_text(encoding="utf-8") == "old"


def test_dashboard_renders_every_panel_from_fixture_data():
    import json
    import re
    import build_dashboard
    panels = [{"id": p["id"], "title": p["title"], "unit": p["unit"], "digits": p["digits"], "zero": False,
               "series": [{"name": s[0], "points": [["2025-01-01", 1.0], ["2025-02-01", 2.0]]} for s in p["series"]]}
              for p in build_dashboard.PANELS]
    page = build_dashboard.render(panels, "2026-11-13")
    data = json.loads(re.search(r'<script type="application/json" id="data">(.*?)</script>', page, re.S).group(1))
    assert [p["id"] for p in data["panels"]] == [p["id"] for p in build_dashboard.PANELS]
    assert all(len(p["series"]) <= 3 for p in data["panels"])              # the palette's all-pairs cap
    assert {t["panel"] for t in data["tiles"]} <= {p["id"] for p in data["panels"]}
    assert "http://" not in page.replace("http://www.w3.org/2000/svg", "") and "https://" not in page    # self-contained
    assert "</script><script>" in page and page.count("<script") == 2
