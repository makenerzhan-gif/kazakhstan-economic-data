"""Per-dataset metadata records.

Every downloaded dataset gets one metadata JSON file under metadata/<agency>/
with exactly the fields required by the MASTER TASK spec (section 4).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
METADATA_ROOT = REPO_ROOT / "metadata"

REQUIRED_FIELDS = [
    "source", "source_url", "dataset_id", "indicator_id", "indicator_name",
    "description", "frequency", "unit", "currency", "geography", "methodology",
    "publication_date", "last_update_date", "download_date", "period_start",
    "period_end", "next_update_date", "transformation", "revision_status",
]


@dataclass
class DatasetMetadata:
    source: str
    source_url: str
    dataset_id: str
    indicator_id: str
    indicator_name: str
    description: str
    frequency: str
    unit: str
    currency: str
    geography: str
    methodology: str
    publication_date: str | None
    last_update_date: str | None
    download_date: str
    period_start: str | None
    period_end: str | None
    next_update_date: str | None
    transformation: str = "none (raw as published)"
    revision_status: str = "original"

    def validate(self) -> None:
        missing = [f for f in REQUIRED_FIELDS if getattr(self, f, None) is None and f not in
                   ("publication_date", "last_update_date", "period_start", "period_end", "next_update_date")]
        if missing:
            raise ValueError(f"Metadata missing required fields: {missing}")

    def write(self) -> Path:
        self.validate()
        out_dir = METADATA_ROOT / self.source
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{self.indicator_id.lower()}.json"
        path.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")
        return path


def load(agency: str, indicator_id: str) -> dict | None:
    path = METADATA_ROOT / agency / f"{indicator_id.lower()}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
