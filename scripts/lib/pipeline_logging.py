"""Per-run structured logging (MASTER TASK section 13).

Every update_*.py run appends one JSON-lines record per action to logs/, with
timestamp, source, dataset, action, status, counts, errors, warnings.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LOGS_ROOT = REPO_ROOT / "logs"


@dataclass
class LogEntry:
    timestamp: str
    source: str
    dataset: str
    action: str
    status: str  # "ok" | "error" | "skipped" | "structural_change"
    records_downloaded: int = 0
    records_processed: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class RunLogger:
    def __init__(self, run_timestamp: str):
        self.run_timestamp = run_timestamp
        self.entries: list[LogEntry] = []
        LOGS_ROOT.mkdir(parents=True, exist_ok=True)
        self.path = LOGS_ROOT / f"run_{run_timestamp.replace(':', '-')}.jsonl"

    def log(self, entry: LogEntry) -> None:
        self.entries.append(entry)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(entry), ensure_ascii=False) + "\n")

    def has_errors(self) -> bool:
        return any(e.status == "error" for e in self.entries)
