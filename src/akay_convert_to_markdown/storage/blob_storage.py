"""Asynchronous, streaming Blob Storage access."""

from __future__ import annotations

from pathlib import Path

from azure.core.exceptions import AzureError, ResourceNotFoundError
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
        client = BlobServiceClient(settings.azure_storage_account_url, credential=credential)
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
        except ResourceNotFoundError as exc:
            raise SourceBlobNotFoundError(f"Source blob '{blob_name}' does not exist.") from exc
        except AzureError as exc:
            raise BlobStorageError(f"Failed to read blob properties: {exc}") from exc
        except Exception as exc:
            raise BlobStorageError(f"Failed to read blob properties: {exc}") from exc
        return properties.size

    async def download_to_file(self, container: str, blob_name: str, destination: Path) -> None:
        """Stream a blob to a local file."""
        try:
            blob = self._client.get_blob_client(container, blob_name)
            downloader = await blob.download_blob()
            with destination.open("wb") as stream:
                await downloader.readinto(stream)
        except ResourceNotFoundError as exc:
            raise SourceBlobNotFoundError(f"Source blob '{blob_name}' does not exist.") from exc
        except AzureError as exc:
            raise BlobStorageError(f"Failed to download blob: {exc}") from exc
        except Exception as exc:
            raise BlobStorageError(f"Failed to download blob: {exc}") from exc

    async def upload_file(self, container: str, blob_name: str, source: Path) -> None:
        """Upload a local file to a blob, overwriting any existing content.

        All destination failures (including a missing container, auth errors,
        throttling and 5xx) are infrastructure/transient and never mark the
        document as permanently failed.
        """
        try:
            blob = self._client.get_blob_client(container, blob_name)
            with source.open("rb") as stream:
                await blob.upload_blob(stream, overwrite=True)
        except AzureError as exc:
            raise BlobStorageError(f"Failed to upload blob: {exc}") from exc
        except Exception as exc:
            raise BlobStorageError(f"Failed to upload blob: {exc}") from exc

    async def aclose(self) -> None:
        await self._client.close()
