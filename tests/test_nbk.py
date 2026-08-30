import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import update_nbk


def test_fetchers_registered_for_every_indicator():
    """See tests/test_bns.py for why this doesn't call the fetchers themselves."""
    assert set(update_nbk.FETCHERS.keys()) == set(update_nbk.INDICATOR_IDS)
    for indicator_id, fn in update_nbk.FETCHERS.items():
        assert callable(fn), f"{indicator_id}'s fetcher is not callable"
