"""Blob Storage wrapper tests (Azure SDK faked)."""

from __future__ import annotations

import pytest
from azure.core.exceptions import (
    ClientAuthenticationError,
    HttpResponseError,
    ResourceNotFoundError,
    ServiceRequestError,
)

from akay_convert_to_markdown.errors.exceptions import BlobStorageError, SourceBlobNotFoundError
from akay_convert_to_markdown.storage.blob_storage import BlobStorage


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

    def get_blob_client(self, container: str, blob_name: str):
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
