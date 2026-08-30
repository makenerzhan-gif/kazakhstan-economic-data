import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import update_nbk
from lib import pipeline_logging


def test_run_logs_skipped_for_unconfirmed_indicators():
    logger = pipeline_logging.RunLogger(run_timestamp="test-run-nbk")
    update_nbk.run(logger)
    assert len(logger.entries) == len(update_nbk.INDICATOR_IDS)
    for e in logger.entries:
        if e.dataset not in update_nbk.FETCHERS:
            assert e.status == "skipped"
    assert not logger.has_errors()
