"""Append-only storage for raw downloads.

Raw files are never overwritten and never modified after being written. A save
is stamped with the download date so a source that revises history is captured
as a new, separate file rather than clobbering what we already had; bytes that
are already archived (same agency, any indicator, any day) are not written a
second time -- the indicator's dated manifest names the file that holds them.
If a same-day re-download comes back byte-identical, nothing new is written
(idempotent). If it comes back with DIFFERENT content -- the source
republished intraday, e.g. a local run earlier today followed by a scheduled
CI run later the same day picking up a fresh revision -- the new content is
archived under a time-suffixed filename rather than raising: the old file is
still never touched or lost, and the pipeline keeps running instead of
hard-failing on a legitimate, expected event (MASTER TASK section 3: "если
источник задним числом поменял ранее опубликованное значение — сохраняй
новую версию отдельно, старую не трогай").
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_ROOT = REPO_ROOT / "data" / "raw"


def raw_path(agency: str, indicator_id: str, download_date: date, ext: str) -> Path:
    """Path for a raw file, e.g. data/raw/bns/bns_gdp_real_2026-08-30.csv"""
    fname = f"{agency}_{indicator_id.lower()}_{download_date.isoformat()}.{ext.lstrip('.')}"
    return RAW_ROOT / agency / fname


def _versioned_raw_path(agency: str, indicator_id: str, download_date: date, ext: str) -> Path:
    """A same-day, content-differing re-download gets a time-suffixed filename (HHMMSS)
    so it never collides with, or overwrites, the file already archived for this date.
    Falls back to a counter suffix in the pathologically unlikely case two such
    revisions land in the same second.
    """
    suffix = datetime.now().strftime("%H%M%S")
    fname = f"{agency}_{indicator_id.lower()}_{download_date.isoformat()}_{suffix}.{ext.lstrip('.')}"
    path = RAW_ROOT / agency / fname
    n = 1
    while path.exists():
        fname = f"{agency}_{indicator_id.lower()}_{download_date.isoformat()}_{suffix}-{n}.{ext.lstrip('.')}"
        path = RAW_ROOT / agency / fname
        n += 1
    return path


def identical_twin(agency: str, ext: str, content: bytes) -> Path | None:
    """A file already archived for this agency -- under ANY indicator id, on ANY day --
    with exactly these bytes. Several indicators read one source file (the 65 MB BNS
    export workbook feeds EXPORTS, the oil-export series and the commodity-group
    datasets; NBK forms carry up to seven series each), and most files do not change
    from one daily run to the next: by 2026-09-15 the store held 11.2 GB, of which
    9.9 GB were byte-identical copies (removed that day, see data/raw/dedup_2026-09-15.json).
    One copy per distinct content is enough: the dated manifest of every indicator still
    records that the download happened, and `raw_file` in it names the file that holds
    the bytes. A source that revises a file produces different bytes and a new file, as
    before -- nothing already archived is ever modified or removed here."""
    folder = RAW_ROOT / agency
    if not folder.exists():
        return None
    size = len(content)
    for p in sorted(folder.glob(f"{agency}_*.{ext.lstrip('.')}")):
        if p.stat().st_size == size and p.read_bytes() == content:
            return p
    return None


same_day_twin = None  # removed 2026-09-15 in favour of identical_twin (any day)


def save_raw_bytes(agency: str, indicator_id: str, download_date: date, ext: str, content: bytes) -> Path:
    """Write raw content to disk and return the path that holds it.

    - No file yet for this (agency, indicator, date): write it normally -- unless a
      file with byte-identical content is already archived for this agency (any
      indicator, any day), in which case that file is returned and nothing new is
      written (see identical_twin).
    - Existing file, byte-identical content: no-op, return the existing path
      (idempotent re-run).
    - Existing file, DIFFERENT content: archive the new content separately
      under a time-suffixed filename (see _versioned_raw_path) and print a
      visible note -- the old file is never modified or deleted. This is the
      normal, expected path for "the source republished intraday," not an
      error condition, so it does not raise.
    """
    path = raw_path(agency, indicator_id, download_date, ext)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = path.read_bytes()
        if existing == content:
            return path  # idempotent re-run same day, nothing to do
        twin = identical_twin(agency, ext, content)
        if twin is not None:
            return twin
        versioned_path = _versioned_raw_path(agency, indicator_id, download_date, ext)
        versioned_path.write_bytes(content)
        print(
            f"raw_store: {path.name} already existed for {download_date.isoformat()} with "
            f"different content -- archived the new version separately as "
            f"{versioned_path.name} (original file untouched)."
        )
        return versioned_path
    twin = identical_twin(agency, ext, content)
    if twin is not None:
        print(f"raw_store: {indicator_id} {download_date.isoformat()}: identical bytes already archived as {twin.name} -- not stored again.")
        return twin
    path.write_bytes(content)
    return path


def latest_raw_file(agency: str, indicator_id: str) -> Path | None:
    """Most recent raw file on disk for this (agency, indicator), by filename date."""
    pattern = f"{agency}_{indicator_id.lower()}_*"
    candidates = sorted((RAW_ROOT / agency).glob(pattern)) if (RAW_ROOT / agency).exists() else []
    return candidates[-1] if candidates else None


def sha256_of(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def is_identical_to_latest(agency: str, indicator_id: str, content: bytes) -> bool:
    latest = latest_raw_file(agency, indicator_id)
    if latest is None:
        return False
    return sha256_of(latest.read_bytes()) == sha256_of(content)


def write_download_manifest(agency: str, indicator_id: str, download_date: date, info: dict) -> Path:
    """Small JSON sidecar recording what was downloaded from where — feeds metadata generation."""
    path = RAW_ROOT / agency / f"{agency}_{indicator_id.lower()}_{download_date.isoformat()}.manifest.json"
    path.write_text(json.dumps(info, indent=2, ensure_ascii=False), encoding="utf-8")
    return path
