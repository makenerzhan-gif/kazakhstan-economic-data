import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import update_minfin


def test_fetchers_registered_for_every_indicator():
    """See tests/test_bns.py for why this doesn't call the fetchers themselves."""
    assert set(update_minfin.FETCHERS.keys()) == set(update_minfin.INDICATOR_IDS)
    for indicator_id, fn in update_minfin.FETCHERS.items():
        assert callable(fn), f"{indicator_id}'s fetcher is not callable"
