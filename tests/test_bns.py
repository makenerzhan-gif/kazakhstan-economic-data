import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import update_bns


def test_fetchers_registered_for_every_indicator():
    """All 8 BNS stage-1 indicators are confirmed and wired -- this catches a
    typo'd key or an indicator silently falling out of FETCHERS. Does NOT call
    the fetchers themselves (that would hit the network on every test run);
    see tests/test_schema.py etc. for offline coverage of the shared logic
    each fetcher relies on.
    """
    assert set(update_bns.FETCHERS.keys()) == set(update_bns.INDICATOR_IDS)
    for indicator_id, fn in update_bns.FETCHERS.items():
        assert callable(fn), f"{indicator_id}'s fetcher is not callable"
