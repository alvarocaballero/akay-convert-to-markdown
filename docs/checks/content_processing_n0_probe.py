"""Recheck N0's pinned APIs and decision vectors without inference or services."""

from __future__ import annotations

import json
import runpy
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

from docling.datamodel.backend_options import (
    HTMLBackendOptions,
    MarkdownBackendOptions,
    PdfBackendOptions,
    ThreadedDoclingParseBackendOptions,
)
from docling.datamodel.base_models import ConfidenceReport
from docling.datamodel.document import ConversionResult
from docling.datamodel.pipeline_options import PdfPipelineOptions


def main() -> None:
    docs = Path(__file__).resolve().parents[1]
    # Reuse the preserved T0 probe; do not duplicate its synthetic export checks.
    runpy.run_path(str(docs / "versión old" / "checks" / "docling_t0_api_probe.py"),
                   run_name="__main__")

    assert ConversionResult.model_fields["confidence"].annotation is ConfidenceReport
    for options_type in (PdfPipelineOptions, PdfBackendOptions, ThreadedDoclingParseBackendOptions):
        assert "replace_broken_text_layer" not in options_type.model_fields
    for options_type in (HTMLBackendOptions, MarkdownBackendOptions):
        options = options_type()
        assert not options.fetch_images
        assert not options.enable_remote_fetch
        assert not options.enable_local_fetch

    # These vectors freeze the N0 decision only. N4 implements the shared ID helper.
    namespace = UUID("bdac804b-e605-5299-872e-42443fecc0c9")
    assert uuid5(NAMESPACE_URL, "urn:akay:convert-to-markdown:section:v1") == namespace
    vectors = [
        ("topic-content:501", "#/texts/0", "c1a3cc1f-4beb-5058-ba1e-51af764fccd7"),
        ("topic-content:501", "#/texts/1", "7172ce0f-1a0b-5376-a8ed-871bbb1227fc"),
        ("manual:\u00e1", "#/texts/0", "59db2df5-39db-5dad-abdf-677402b8512d"),
    ]
    for content_key, item_ref, expected in vectors:
        name = json.dumps(["section-v1", content_key, item_ref],
                          ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        assert str(uuid5(namespace, name)) == expected

    print("PASS: conversion confidence, backend boundaries, unavailable repair flag, section UUID vectors")


if __name__ == "__main__":
    main()
