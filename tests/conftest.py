"""Shared test setup.

The data sync pushes to GitHub, and the repo is public, so no test may ever
reach it by accident (one did, through the runner loop, before this guard
existed): every test starts with the sync turned off and git calls from
datasync refused. tests/test_datasync.py turns both back on against local
stand-ins for GitHub.
"""

import pytest

from orbit import datasync, outputs
from orbit.config import settings


def _refuse(*args, **kwargs):
    raise AssertionError("a test tried to run git for the data sync; use the Machines fixture in test_datasync.py")


@pytest.fixture(autouse=True)
def no_real_data_sync(monkeypatch):
    monkeypatch.setattr(datasync, "DATA_SYNC_ENABLED", False)
    monkeypatch.setattr(settings, "DATA_SYNC_JOURNAL", False)  # whatever this machine's .env says
    monkeypatch.setattr(datasync, "_git", _refuse)
    monkeypatch.setattr(outputs, "_remote_url", _refuse)  # results sharing too; test_outputs.py points it at a local repo
    monkeypatch.setenv("ORBIT_DATA_SYNC", "0")  # for any subprocess a test starts
