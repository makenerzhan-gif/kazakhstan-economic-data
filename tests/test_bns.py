import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import update_bns
from lib import pipeline_logging


def test_run_logs_skipped_for_unconfirmed_indicators():
    """Until config/sources.yaml has confirmed BNS endpoints, every indicator
    must log status=skipped rather than error or silently doing nothing."""
    logger = pipeline_logging.RunLogger(run_timestamp="test-run-bns")
    update_bns.run(logger)
    assert len(logger.entries) == len(update_bns.INDICATOR_IDS)
    for e in logger.entries:
        if e.dataset not in update_bns.FETCHERS:
            assert e.status == "skipped"
    assert not logger.has_errors()
