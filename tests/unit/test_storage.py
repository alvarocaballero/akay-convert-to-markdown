"""Blob Storage wrapper tests (Azure SDK faked)."""

from __future__ import annotations

import pytest
import logging
import traceback
from azure.core.exceptions import (
    ClientAuthenticationError,
    HttpResponseError,
    ResourceNotFoundError,
    ServiceRequestError,
)

from akay_convert_to_markdown.errors.exceptions import BlobStorageError, SourceBlobNotFoundError
from akay_convert_to_markdown.storage.blob_storage import BlobStorage
from tests.helpers import make_settings


class FakeDownloader:
    def __init__(self, data: bytes) -> None:
        self.data = data

    async def readinto(self, stream) -> None:
        stream.write(self.data)


class FakeBlobClient:
    def __init__(
        self,
        *,
        size: int | None = None,
        missing: bool = False,
        data: bytes = b"content",
        get_error: Exception | None = None,
        download_error: Exception | None = None,
        upload_error: Exception | None = None,
    ) -> None:
        self.size = size
        self.missing = missing
        self.data = data
        self.get_error = get_error
        self.download_error = download_error
        self.upload_error = upload_error
        self.uploaded: bytes | None = None

    def _raise_or_not_found(self, error: Exception | None) -> None:
        if error:
            raise error
        if self.missing:
            raise ResourceNotFoundError("not found")

    async def get_blob_properties(self):
        self._raise_or_not_found(self.get_error)
        return type("BlobProperties", (), {"size": self.size})()

    async def download_blob(self):
        self._raise_or_not_found(self.download_error)
        return FakeDownloader(self.data)

    async def upload_blob(self, stream, overwrite: bool = False) -> None:
        if self.upload_error:
            raise self.upload_error
        self.uploaded = stream.read()


class FakeServiceClient:
    def __init__(self, blob: FakeBlobClient) -> None:
        self.blob = blob
        self.closed = False
        self.calls = []

    def get_blob_client(self, container: str, blob_name: str):
        self.calls.append((container, blob_name))
        return self.blob

    async def close(self) -> None:
        self.closed = True


def _make_storage(blob: FakeBlobClient) -> BlobStorage:
    return BlobStorage(FakeServiceClient(blob))


async def test_source_exists_returns_size():
    storage = _make_storage(FakeBlobClient(size=1234))
    assert await storage.get_blob_size("source", "x/y.pdf") == 1234


async def test_source_missing_raises_not_found():
    storage = _make_storage(FakeBlobClient(missing=True))
    with pytest.raises(SourceBlobNotFoundError):
        await storage.get_blob_size("source", "x/y.pdf")


async def test_download_writes_file(tmp_path):
    storage = _make_storage(FakeBlobClient(data=b"PDFDATA"))
    dest = tmp_path / "source.pdf"
    await storage.download_to_file("source", "x/y.pdf", dest)
    assert dest.read_bytes() == b"PDFDATA"


async def test_upload_calls_blob_with_overwrite(tmp_path):
    blob = FakeBlobClient()
    storage = _make_storage(blob)
    src = tmp_path / "document.md"
    src.write_text("# hello")
    await storage.upload_file("markdown", "ctx/doc/document.md", src)
    assert blob.uploaded == b"# hello"


# --- Error classification ----------------------------------------------------

async def test_source_404_is_permanent():
    storage = _make_storage(FakeBlobClient(missing=True))
    with pytest.raises(SourceBlobNotFoundError):
        await storage.get_blob_size("source", "x/y.pdf")


async def test_source_401_is_transient():
    storage = _make_storage(FakeBlobClient(get_error=ClientAuthenticationError("unauthorized")))
    with pytest.raises(BlobStorageError):
        await storage.get_blob_size("source", "x/y.pdf")


async def test_source_403_is_transient(tmp_path):
    storage = _make_storage(FakeBlobClient(download_error=ClientAuthenticationError("forbidden")))
    with pytest.raises(BlobStorageError):
        await storage.download_to_file("source", "x/y.pdf", tmp_path / "source.pdf")


@pytest.mark.parametrize(
    "error",
    [
        HttpResponseError("rate limited"),
        HttpResponseError("service unavailable"),
        ServiceRequestError("network error"),
    ],
)
async def test_source_429_5xx_network_is_transient(error, tmp_path):
    storage = _make_storage(FakeBlobClient(get_error=error))
    with pytest.raises(BlobStorageError):
        await storage.get_blob_size("source", "x/y.pdf")


async def test_destination_container_missing_is_transient(tmp_path):
    src = tmp_path / "document.md"
    src.write_text("# hello")
    storage = _make_storage(FakeBlobClient(upload_error=ResourceNotFoundError("container not found")))
    with pytest.raises(BlobStorageError):
        await storage.upload_file("markdown", "ctx/doc/document.md", src)


async def test_destination_401_is_transient(tmp_path):
    src = tmp_path / "document.md"
    src.write_text("# hello")
    storage = _make_storage(FakeBlobClient(upload_error=ClientAuthenticationError("forbidden")))
    with pytest.raises(BlobStorageError):
        await storage.upload_file("markdown", "ctx/doc/document.md", src)


@pytest.mark.parametrize("token,expected_sas", [(None, None), ("", None), ("  ", None),
                                                ("sv=1&sig=secret", "sv=1&sig=secret"),
                                                ("?sv=1&sig=secret", "sv=1&sig=secret")])
async def test_client_uses_sas_or_shared_credential(monkeypatch, token, expected_sas):
    credential = object()
    service = FakeServiceClient(FakeBlobClient())
    calls = []

    def create_client(account_url, credential):
        calls.append((account_url, credential))
        return service

    monkeypatch.setattr("akay_convert_to_markdown.storage.blob_storage.BlobServiceClient", create_client)
    settings = make_settings(azure_storage_sas_token=token)
    storage = BlobStorage.from_settings(settings, credential)
    assert calls == [(settings.azure_storage_account_url, expected_sas or credential)]
    await storage.aclose()
    assert service.closed


async def test_read_and_write_keep_container_and_blob_names(tmp_path):
    service = FakeServiceClient(FakeBlobClient())
    storage = BlobStorage(service)
    path = tmp_path / "document"
    await storage.download_to_file("topic-content", "source/file.pdf", path)
    await storage.upload_file("topic-content", "destination/file.md", path)
    assert service.calls == [("topic-content", "source/file.pdf"),
                             ("topic-content", "destination/file.md")]


@pytest.mark.parametrize("operation", ["properties", "exists", "download", "upload", "missing", "init"])
async def test_storage_error_does_not_expose_sas(monkeypatch, tmp_path, caplog, operation):
    token = "sv=1&sig=secret-value"
    error = ClientAuthenticationError(f"https://example.blob.core.windows.net/blob?{token}")
    if operation == "missing":
        error = ResourceNotFoundError(f"https://example.blob.core.windows.net/blob?{token}")
    blob = FakeBlobClient(get_error=error, download_error=error, upload_error=error)
    storage = _make_storage(blob)
    path = tmp_path / "document"
    path.write_text("content")
    with caplog.at_level(logging.ERROR):
        try:
            if operation == "properties" or operation == "missing":
                await storage.get_blob_size("source", "file.pdf")
            elif operation == "exists":
                await storage.blob_exists("source", "file.pdf")
            elif operation == "download":
                await storage.download_to_file("source", "file.pdf", path)
            elif operation == "upload":
                await storage.upload_file("destination", "file.md", path)
            else:
                def fail_client(*args, **kwargs):
                    raise error
                monkeypatch.setattr("akay_convert_to_markdown.storage.blob_storage.BlobServiceClient", fail_client)
                BlobStorage.from_settings(make_settings(azure_storage_sas_token=token), object())
        except (BlobStorageError, SourceBlobNotFoundError) as exc:
            logging.exception("Storage failed")
            assert token not in str(exc)
            assert token not in "".join(traceback.format_exception(exc))
        else:
            pytest.fail("Storage error was not raised")
    assert token not in caplog.text
