"""Asynchronous, streaming Blob Storage access."""

from __future__ import annotations

from pathlib import Path

from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError
from azure.identity.aio import DefaultAzureCredential
from azure.storage.blob.aio import BlobServiceClient

from akay_convert_to_markdown.config.settings import Settings
from akay_convert_to_markdown.errors.exceptions import BlobStorageError, SourceBlobNotFoundError


class BlobStorage:
    """Streaming wrapper around Azure Blob Storage.

    Documents are downloaded and uploaded through file streams so the worker
    never holds an entire source document in memory.
    """

    def __init__(self, service_client: BlobServiceClient) -> None:
        self._client = service_client

    @classmethod
    def from_settings(cls, settings: Settings, credential: DefaultAzureCredential) -> "BlobStorage":
        try:
            client = BlobServiceClient(settings.azure_storage_account_url,
                                       credential=settings.azure_storage_sas_token or credential)
        except Exception:
            raise BlobStorageError("Failed to initialize Blob Storage client.") from None
        return cls(client)

    async def get_blob_size(self, container: str, blob_name: str) -> int:
        """Return the source blob size in bytes.

        A 404 on the source blob is a permanent document error
        (:class:`SourceBlobNotFoundError`); every other failure (auth, throttling,
        5xx, network, ...) is infrastructure/transient (:class:`BlobStorageError`).
        """
        try:
            blob = self._client.get_blob_client(container, blob_name)
            properties = await blob.get_blob_properties()
        except ResourceNotFoundError:
            raise SourceBlobNotFoundError(f"Source blob '{blob_name}' does not exist.") from None
        except Exception:
            raise BlobStorageError("Failed to read blob properties.") from None
        return properties.size

    async def blob_exists(self, container: str, blob_name: str) -> bool:
        """Whether a blob exists (used for idempotent reprocessing).

        A 404 simply means "not yet produced"; any other failure is treated as
        transient infrastructure (:class:`BlobStorageError`).
        """
        try:
            blob = self._client.get_blob_client(container, blob_name)
            await blob.get_blob_properties()
        except ResourceNotFoundError:
            return False
        except Exception:
            raise BlobStorageError("Failed to check blob existence.") from None
        return True

    async def download_to_file(self, container: str, blob_name: str, destination: Path) -> None:
        """Stream a blob to a local file."""
        try:
            blob = self._client.get_blob_client(container, blob_name)
            downloader = await blob.download_blob()
            with destination.open("wb") as stream:
                await downloader.readinto(stream)
        except ResourceNotFoundError:
            raise SourceBlobNotFoundError(f"Source blob '{blob_name}' does not exist.") from None
        except Exception:
            raise BlobStorageError("Failed to download blob.") from None

    async def upload_file(self, container: str, blob_name: str, source: Path, *, overwrite: bool = False) -> None:
        """Upload a local file, atomically preserving an existing blob when requested.

        All destination failures (including a missing container, auth errors,
        throttling and 5xx) are infrastructure/transient and never mark the
        document as permanently failed.
        """
        try:
            blob = self._client.get_blob_client(container, blob_name)
            with source.open("rb") as stream:
                await blob.upload_blob(stream, overwrite=overwrite)
        except ResourceExistsError:
            if overwrite:
                raise BlobStorageError("Failed to overwrite destination blob.") from None
        except Exception:
            raise BlobStorageError("Failed to upload blob.") from None

    async def aclose(self) -> None:
        await self._client.close()
