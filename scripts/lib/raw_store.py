"""Append-only storage for raw downloads.

Raw files are never overwritten and never modified after being written. Every
save is stamped with the download date so a source that revises history is
captured as a new, separate file rather than clobbering what we already had.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_ROOT = REPO_ROOT / "data" / "raw"


def raw_path(agency: str, indicator_id: str, download_date: date, ext: str) -> Path:
    """Path for a raw file, e.g. data/raw/bns/bns_gdp_real_2026-08-30.csv"""
    fname = f"{agency}_{indicator_id.lower()}_{download_date.isoformat()}.{ext.lstrip('.')}"
    return RAW_ROOT / agency / fname


def save_raw_bytes(agency: str, indicator_id: str, download_date: date, ext: str, content: bytes) -> Path:
    """Write raw content to disk. Refuses to overwrite an existing file for the same
    (agency, indicator, date) — if a second download happens same day, the caller must
    verify identical content (see is_identical_to_latest) rather than blindly re-saving.
    """
    path = raw_path(agency, indicator_id, download_date, ext)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = path.read_bytes()
        if existing == content:
            return path  # idempotent re-run same day, nothing to do
        raise FileExistsError(
            f"{path} already exists with different content for the same date. "
            "Raw files are append-only; investigate before overwriting."
        )
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
