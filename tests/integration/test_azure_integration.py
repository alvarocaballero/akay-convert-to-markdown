"""Optional integration tests against developer Azure resources.

These tests are disabled by default and only run when the environment variable
``RUN_AZURE_INTEGRATION_TESTS`` is set to ``true``. They rely on
``DefaultAzureCredential`` (e.g. Azure CLI developer credentials) and therefore
do not require secrets or connection strings.

Required environment variables mirror the worker configuration (see README).
"""

from __future__ import annotations

import os
import uuid

import pytest
from azure.identity.aio import DefaultAzureCredential

from akay_convert_to_markdown.config.settings import Settings
from akay_convert_to_markdown.storage.blob_storage import BlobStorage

RUN = os.environ.get("RUN_AZURE_INTEGRATION_TESTS", "").strip().lower() == "true"

pytestmark = pytest.mark.skipif(
    not RUN,
    reason="Set RUN_AZURE_INTEGRATION_TESTS=true to run against Azure.",
)


@pytest.fixture
def azure_settings() -> Settings:
    return Settings()


@pytest.fixture
def credential():
    return DefaultAzureCredential()


async def test_blob_round_trip(azure_settings, credential, tmp_path):
    async with credential:
        storage = BlobStorage.from_settings(azure_settings, credential)
        blob_name = f"it/{uuid.uuid4()}/document.md"
        source = tmp_path / "document.md"
        source.write_text("# integration test")

        await storage.upload_file(azure_settings.destination_container_name, blob_name, source)

        downloaded = tmp_path / "downloaded.md"
        await storage.download_to_file(azure_settings.destination_container_name, blob_name, downloaded)

        assert downloaded.read_text() == "# integration test"
        await storage.aclose()
