"""
tests/conftest.py -- shared pytest fixtures.

server.py reads its configuration from environment variables at
*import* time (see the "Configuration" section near the top of
server.py), so tests set env vars first and then import/reload the
module -- there's no way to reconfigure it after the fact without
that reload.

Rather than hitting a real printer, these tests point
DAVINCI_MINIMOVER_BIN at a small fake `minimover` (fixtures/fake_minimover.py)
that mimics the real CLI's three subcommands (-c convert, -p print,
-s status) well enough to exercise the whole upload -> convert ->
print pipeline for real through Flask, with no hardware involved.
"""

import importlib
import os
import stat
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
FAKE_MINIMOVER_SRC = Path(__file__).resolve().parent / "fixtures" / "fake_minimover.py"

sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture
def fake_minimover(tmp_path):
    """Install an executable fake `minimover` under tmp_path and return its path."""
    dest = tmp_path / "minimover"
    dest.write_text(FAKE_MINIMOVER_SRC.read_text())
    dest.chmod(dest.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return dest


@pytest.fixture
def app_client(tmp_path, monkeypatch, fake_minimover):
    """A Flask test client backed by a fresh server module import, using
    the fake minimover and a scratch upload directory. No DAVINCI_API_KEY."""
    upload_dir = tmp_path / "uploads"
    monkeypatch.setenv("DAVINCI_UPLOAD_DIR", str(upload_dir))
    monkeypatch.setenv("DAVINCI_DEVICE", str(tmp_path / "fake-device"))
    monkeypatch.setenv("DAVINCI_MINIMOVER_BIN", str(fake_minimover))
    monkeypatch.delenv("DAVINCI_API_KEY", raising=False)
    monkeypatch.setenv("DAVINCI_PRINTER", "davinci_1_0_pro")

    import server  # noqa: PLC0415
    importlib.reload(server)  # picks up the env vars set above

    server.app.config["TESTING"] = True
    with server.app.test_client() as client:
        yield client, server


@pytest.fixture
def app_client_with_api_key(tmp_path, monkeypatch, fake_minimover):
    """Same as app_client, but with DAVINCI_API_KEY set, for auth tests."""
    upload_dir = tmp_path / "uploads"
    monkeypatch.setenv("DAVINCI_UPLOAD_DIR", str(upload_dir))
    monkeypatch.setenv("DAVINCI_DEVICE", str(tmp_path / "fake-device"))
    monkeypatch.setenv("DAVINCI_MINIMOVER_BIN", str(fake_minimover))
    monkeypatch.setenv("DAVINCI_API_KEY", "test-secret-key")
    monkeypatch.setenv("DAVINCI_PRINTER", "davinci_1_0_pro")

    import server  # noqa: PLC0415
    importlib.reload(server)

    server.app.config["TESTING"] = True
    with server.app.test_client() as client:
        yield client, server
