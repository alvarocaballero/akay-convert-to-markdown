"""Pytest fixtures."""

from __future__ import annotations

import pytest

from tests.helpers import FakeConverter, FakeStorage, FakeWebhook, make_settings


@pytest.fixture
def settings(tmp_path):
    return make_settings(temp_directory=tmp_path / "akay")


@pytest.fixture
def fake_storage():
    return FakeStorage()


@pytest.fixture
def fake_converter():
    return FakeConverter()


@pytest.fixture
def fake_webhook():
    return FakeWebhook()
