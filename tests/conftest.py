"""Shared pytest configuration."""


def pytest_configure(config):
    # A cross-source check compares two publications that each take a revision up at
    # their own pace (NBK and the IMF, two NBK forms, two BNS releases), so a failure may
    # mean only that one is behind the other. scripts/update_all.py runs these separately:
    # a failure is reported as a warning and in the update report, and the day's data is
    # still committed. Every other test blocks the commit.
    config.addinivalue_line(
        "markers",
        "cross_source: compares two publications that revise on their own schedules; "
        "reported by update_all.py, never blocks the daily commit",
    )
