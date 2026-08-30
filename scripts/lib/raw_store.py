"""Append-only storage for raw downloads.

Raw files are never overwritten and never modified after being written. Every
save is stamped with the download date so a source that revises history is
captured as a new, separate file rather than clobbering what we already had.
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


def save_raw_bytes(agency: str, indicator_id: str, download_date: date, ext: str, content: bytes) -> Path:
    """Write raw content to disk.

    - No file yet for this (agency, indicator, date): write it normally.
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
        versioned_path = _versioned_raw_path(agency, indicator_id, download_date, ext)
        versioned_path.write_bytes(content)
        print(
            f"raw_store: {path.name} already existed for {download_date.isoformat()} with "
            f"different content -- archived the new version separately as "
            f"{versioned_path.name} (original file untouched)."
        )
        return versioned_path
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
