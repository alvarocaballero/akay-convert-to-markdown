"""Ordered index/delete worker; fail closed before clients if configuration is absent."""

from __future__ import annotations

import logging

from akay_convert_to_markdown.config.settings import IndexerSettings
from akay_convert_to_markdown.logging import configure_logging


def build_processor(settings, storage, webhook, logger, *, config, embedding_settings, token_provider=None):
    # Heavy/index-only dependencies are loaded after explicit configuration.
    from qdrant_client import AsyncQdrantClient
    from akay_convert_to_markdown.indexing.azure_embeddings import AzureOpenAIEmbeddings
    from akay_convert_to_markdown.indexing.point_sets import PointSetIndexer, QdrantPointStore
    from akay_convert_to_markdown.indexing.profiles import ProfileCatalog
    from akay_convert_to_markdown.indexing.tokenizer import Cl100kTokenizer
    from akay_convert_to_markdown.processing.index_processor import IndexProcessor

    catalog = ProfileCatalog(config.profiles)
    tokenizer = Cl100kTokenizer.from_file(config.tokenizer_path)
    if embedding_settings.auth_mode == "entra" and token_provider is None:
        raise ValueError("Entra requires an explicitly supplied async token provider.")
    for profile in config.profiles:
        if profile.deployment != embedding_settings.deployment:
            raise ValueError("Profile deployments must match the configured Azure adapter.")
    client = AsyncQdrantClient(url=config.qdrant_url, prefer_grpc=False, check_compatibility=False, trust_env=False,
                               timeout=config.qdrant_timeout_seconds,
                               api_key=config.qdrant_api_key.get_secret_value() if config.qdrant_api_key else None)
    embeddings = AzureOpenAIEmbeddings(embedding_settings, tokenizer=tokenizer, token_provider=token_provider)
    indexer = PointSetIndexer(catalog, embeddings, QdrantPointStore(client), tokenizer=tokenizer,
                              tokenizer_id="cl100k_base", batch_size=config.batch_size, max_chunks=config.max_chunks)
    coordinator = storage.ordered_indexer(indexer, state_container=config.state_container, state_prefix=config.state_prefix,
                                          source_container=settings.source_container_name, target_identity=config.qdrant_url,
                                          max_record_bytes=config.max_state_bytes)

    async def close():
        try:
            await embeddings.__aexit__(None, None, None)
        finally:
            await client.close()

    return IndexProcessor(settings, storage, coordinator, webhook), close


def main() -> int:
    settings = IndexerSettings()
    configure_logging(settings.log_level)
    from functools import partial
    from pydantic import ValidationError
    from akay_convert_to_markdown.config.indexing_settings import AzureOpenAISettings, IndexRuntimeSettings

    try:
        config, azure = IndexRuntimeSettings(), AzureOpenAISettings()
        if azure.auth_mode == "entra":
            raise ValueError("CLI requires explicit API-key mode; Entra uses the programmatic token provider.")
    except (ValidationError, ValueError):
        logging.getLogger("akay.index_content").error("worker.configuration_required",
                                                     extra={"error_code": "INDEX_CONFIGURATION_REQUIRED"})
        return 2
    from akay_convert_to_markdown.worker_runtime import run_main

    return run_main(settings, partial(build_processor, config=config, embedding_settings=azure), "akay.index_content")


if __name__ == "__main__":
    raise SystemExit(main())
