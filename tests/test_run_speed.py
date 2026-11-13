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
