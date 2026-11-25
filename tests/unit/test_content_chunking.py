"""N9: offline real HybridChunker, structural boundaries and honest citations."""

import importlib
import json
import os
import socket
import subprocess
import sys
import warnings
from uuid import UUID, uuid5

import pytest
from docling_core.transforms.chunker.tokenizer.base import BaseTokenizer
from docling_core.types.doc import (
    BoundingBox, ContentLayer, DocItemLabel, DoclingDocument, DocumentOrigin,
    ImageRef, ProvenanceItem, RichTableCell, TableCell, TableData,
)

from akay_convert_to_markdown.contracts.requests import parse_request
from akay_convert_to_markdown.errors.exceptions import PermanentError


class CharacterTokenizer(BaseTokenizer):
    """Explicit test-only counting policy; no production model/tokenizer choice."""

    limit: int = 160

    def count_tokens(self, text: str) -> int:
        return len(text)

    def get_max_tokens(self) -> int:
        return self.limit

    def get_tokenizer(self):
        return self.count_tokens


@pytest.fixture
def chunking(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("N9 must not fetch resources or materialize images")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(ImageRef, "pil_image", property(forbidden))
    return importlib.import_module("akay_convert_to_markdown.indexing.chunking")


def request(*, format="docling", mode="none", budget=160, **updates):
    context = {"mode": mode}
    if mode == "fixed":
        context.update(sectionId="8af35178-a031-50c7-9c53-d77084e0c684", headingPath=["Course", "Parent"])
    elif mode == "fromReview":
        context["reviewBlobName"] = "out/document.artifacts/review.json"
    raw = {"schemaVersion": 1, "requestId": "b1ad362f-0911-4773-8651-1508d94ca003",
           "operationSequence": 1, "operation": "index", "contentKey": "opaque:á", "scopeKey": "scope:a",
           "source": {"type": "blob", "format": format,
                      "blobName": "out/document.artifacts/" + ("document.docling.json" if format == "docling" else "transcript.json")},
           "sectionContext": context, "indexProfile": {"id": "test-only", "provider": "TestDouble",
           "model": "test-only", "dimensions": 3, "tokenizer": "test-character-v1", "maxChunkTokens": budget,
           "distance": "Cosine", "collection": "test-only"}, "metadata": {"consumer": "opaque"}, "callback": "fixture"}
    raw.update(updates)
    return parse_request(json.dumps(raw), worker="index", callbacks={"fixture"})


def document():
    doc = DoclingDocument(name="source.pdf", origin=DocumentOrigin(filename="source.pdf", mimetype="application/pdf", binary_hash=7))
    doc.add_text(label=DocItemLabel.TEXT, text="General preamble.")
    first = doc.add_heading("Repeated", level=1)
    doc.add_text(label=DocItemLabel.TEXT, text="First section body.")
    child = doc.add_heading("Nested", level=2)
    doc.add_text(label=DocItemLabel.TEXT, text="Nested body.")
    second = doc.add_heading("Repeated", level=1)
    doc.add_text(label=DocItemLabel.TEXT, text="Second section body.")
    return doc, [first, child, second]


def review(doc, headings, key="opaque:á"):
    sections = []
    for item in headings:
        level = item.level + 1
        parent = next((s for s in reversed(sections) if s["level"] < level), None)
        identity = uuid5(UUID("bdac804b-e605-5299-872e-42443fecc0c9"),
                         json.dumps(["section-v1", key, item.self_ref], ensure_ascii=False, separators=(",", ":")))
        sections.append({"id": str(identity), "parentId": parent["id"] if parent else None,
                         "title": item.text, "level": level, "order": len(sections), "doclingItemRef": item.self_ref})
    return {"schemaVersion": 1, "contentKey": key, "contentType": "document",
            "source": {"type": "blob", "blobName": "inputs/" + doc.name},
            "summary": {"sectionCount": len(sections)}, "sections": sections,
            "processing": {"engine": "docling", "engineVersion": "2.141.0"}}


def run(chunking, req, doc, *, review_data=None, tokenizer=None, tokenizer_id="test-character-v1"):
    raw = json.dumps(doc.export_to_dict(), ensure_ascii=False) if isinstance(doc, DoclingDocument) else json.dumps(doc)
    return chunking.chunk_content(req, raw, tokenizer=tokenizer or CharacterTokenizer(), tokenizer_id=tokenizer_id,
                                  review_raw=None if review_data is None else json.dumps(review_data))


def test_principal_repeated_headings_and_preamble_never_mix(chunking):
    doc, headings = document()
    data = review(doc, headings)
    chunks = run(chunking, request(mode="fromReview"), doc, review_data=data)
    assert [c.text for c in chunks] == ["General preamble.", "First section body.", "Nested body.", "Second section body."]
    assert [str(c.section_id) if c.section_id else None for c in chunks] == [None, *(s["id"] for s in data["sections"])]
    assert [c.heading_path for c in chunks] == [[], ["Repeated"], ["Repeated", "Nested"], ["Repeated"]]
    assert [c.chunk_index for c in chunks] == list(range(4))
    assert all(c.source == request().source and c.origin.blob_name == "inputs/source.pdf" for c in chunks)
    assert chunks[1].provenance.item_refs == [doc.texts[2].self_ref]
    assert chunks[1].provenance.pages == []
    assert all(c.token_count == len(c.contextualized_text) <= 160 for c in chunks)


@pytest.mark.parametrize("mode", ["fixed", "none"])
def test_additional_internal_headings_and_context_count_together(chunking, mode):
    doc = DoclingDocument(name="notes.md")
    doc.add_heading("Internal", level=1)
    text = " ".join(f"word{i}" for i in range(45))
    doc.add_text(label=DocItemLabel.TEXT, text=text)
    req = request(mode=mode, budget=100)
    chunks = run(chunking, req, doc)
    assert len(chunks) > 1
    assert " ".join(c.text for c in chunks).split() == text.split()
    assert all(c.internal_headings == ["Internal"] and c.token_count <= 100 for c in chunks)
    assert all("notes.md" in c.contextualized_text and "Internal" in c.contextualized_text for c in chunks)
    if mode == "fixed":
        assert all(c.section_id == req.section_context.section_id and c.heading_path == ["Course", "Parent"] for c in chunks)
        assert all("Course > Parent" in c.contextualized_text for c in chunks)
    else:
        assert all(c.section_id is None and c.heading_path == [] for c in chunks)


def transcript(segments=None):
    return {"schemaVersion": 1, "contentKey": "opaque:á", "origin": {"type": "youtube", "url": "https://youtu.be/abcdefghijk"},
            "language": "es-ES", "durationMilliseconds": 10000,
            "segments": segments or [{"id": "s1", "text": "First phrase.", "startMilliseconds": 1000,
                                      "endMilliseconds": 2500, "speaker": "0", "language": "es-ES"},
                                     {"id": "s2", "text": "Second phrase.", "startMilliseconds": 3000,
                                      "endMilliseconds": 6000}]}


def test_transcript_merges_segments_retaining_original_ranges_and_origin(chunking):
    chunks = run(chunking, request(format="transcript", mode="fixed", budget=220), transcript(), tokenizer=CharacterTokenizer(limit=220))
    assert len(chunks) == 1 and chunks[0].text == "First phrase.\nSecond phrase."
    chunk = chunks[0]
    assert chunk.origin.url == "https://youtu.be/abcdefghijk"
    assert chunk.source.blob_name.endswith("transcript.json")
    assert chunk.provenance.pages == []
    assert (chunk.provenance.start_milliseconds, chunk.provenance.end_milliseconds) == (1000, 6000)
    assert [s.id for s in chunk.provenance.segments] == ["s1", "s2"]
    assert [s.item_ref for s in chunk.provenance.segments] == ["#/texts/0", "#/texts/1"]
    assert chunk.provenance.segments[0].speaker == "0" and chunk.provenance.segments[0].language == "es-ES"


def test_split_transcript_keeps_whole_phrase_citation_without_invented_word_times(chunking):
    text = " ".join(f"word{i}" for i in range(60))
    data = transcript([{"id": "s1", "text": text, "startMilliseconds": 1200, "endMilliseconds": 9800}])
    chunks = run(chunking, request(format="transcript", budget=110), data)
    assert len(chunks) > 2 and " ".join(c.text for c in chunks).split() == text.split()
    assert all((c.provenance.start_milliseconds, c.provenance.end_milliseconds) == (1200, 9800) for c in chunks)
    assert all([s.id for s in c.provenance.segments] == ["s1"] for c in chunks)
    assert all(c.token_count <= 110 for c in chunks)


@pytest.mark.parametrize("missing", ["startMilliseconds", "endMilliseconds", "both"])
def test_unknown_transcript_times_stay_null_even_when_merged(chunking, missing):
    data = transcript()
    for key in (["startMilliseconds", "endMilliseconds"] if missing == "both" else [missing]):
        data["segments"][1].pop(key)
    chunk = run(chunking, request(format="transcript", budget=300), data, tokenizer=CharacterTokenizer(limit=300))[0]
    assert chunk.provenance.start_milliseconds == (None if missing in {"both", "startMilliseconds"} else 1000)
    assert chunk.provenance.end_milliseconds == (None if missing in {"both", "endMilliseconds"} else 6000)


@pytest.mark.parametrize("uri", ["../../private/secret.png", "file:///private/secret.png", "https://private.invalid/image.png"])
def test_saved_json_never_opens_referenced_images(chunking, uri):
    doc = DoclingDocument(name="source.pdf")
    picture = doc.add_picture()
    data = doc.export_to_dict()
    data["pictures"][0]["image"] = {"uri": uri, "mimetype": "image/png", "dpi": 72, "size": {"width": 8, "height": 8}}
    doc.add_text(label=DocItemLabel.TEXT, text="Safe body.")
    data["texts"] = doc.export_to_dict()["texts"]
    data["body"] = doc.export_to_dict()["body"]
    chunks = run(chunking, request(), data)
    assert [c.text for c in chunks] == ["Safe body."]
    assert uri not in json.dumps([c.model_dump(mode="json") for c in chunks])


def test_pages_item_refs_and_clean_text_survive_splitting(chunking):
    doc = DoclingDocument(name="source.pdf")
    prov = ProvenanceItem(page_no=3, charspan=(0, 200), bbox=BoundingBox(l=0, t=0, r=100, b=100))
    item = doc.add_text(label=DocItemLabel.TEXT, text="A sentence. " * 30, prov=prov)
    chunks = run(chunking, request(budget=90), doc)
    assert len(chunks) > 1
    assert all(c.provenance.pages == [3] and c.provenance.item_refs == [item.self_ref] for c in chunks)
    assert all(c.provenance.start_milliseconds is None and not c.provenance.segments for c in chunks)
    assert all("source.pdf" not in c.text and "source.pdf" in c.contextualized_text for c in chunks)


@pytest.mark.parametrize("change", ["contentKey", "title", "level", "id", "doclingItemRef", "source", "missing", "order"])
def test_foreign_or_inconsistent_review_is_rejected(chunking, change):
    doc, headings = document()
    data = review(doc, headings)
    if change == "contentKey":
        data[change] = "other"
    elif change == "source":
        data[change]["blobName"] = "inputs/foreign.pdf"
    elif change == "missing":
        data["sections"].pop()
        data["summary"]["sectionCount"] -= 1
    elif change == "order":
        data["sections"][0], data["sections"][2] = data["sections"][2], data["sections"][0]
        for i, s in enumerate(data["sections"]):
            s["order"] = i
    else:
        data["sections"][0][change] = {"title": "Foreign", "level": 3, "id": "8af35178-a031-50c7-9c53-d77084e0c684",
                                         "doclingItemRef": "#/texts/999"}[change]
    with pytest.raises(PermanentError):
        run(chunking, request(mode="fromReview"), doc, review_data=data)


def test_review_is_required_and_must_be_in_the_same_artifact_namespace(chunking):
    doc, headings = document()
    with pytest.raises(PermanentError):
        run(chunking, request(mode="fromReview"), doc)
    req = request(sectionContext={"mode": "fromReview", "reviewBlobName": "foreign/review.json"})
    with pytest.raises(PermanentError):
        run(chunking, req, doc, review_data=review(doc, headings))


@pytest.mark.parametrize("change", ["key", "negative", "empty", "duplicate", "reversed"])
def test_invalid_transcripts_do_not_yield_partial_chunks(chunking, change):
    data = transcript()
    if change == "key":
        data["contentKey"] = "foreign"
    elif change == "negative":
        data["segments"][0]["startMilliseconds"] = -1
    elif change == "empty":
        data["segments"] = []
    elif change == "duplicate":
        data["segments"][1]["id"] = "s1"
    else:
        data["segments"].reverse()
    with pytest.raises(PermanentError):
        run(chunking, request(format="transcript"), data)


@pytest.mark.parametrize("raw", ['{"name":"a","name":"b"}', '{"name":NaN}', '{"name":Infinity}', 'not json'])
def test_strict_docling_json_boundary(chunking, raw):
    with pytest.raises(PermanentError) as error:
        chunking.chunk_content(request(), raw, tokenizer=CharacterTokenizer(), tokenizer_id="test-character-v1")
    assert "NaN" not in str(error.value) and "not json" not in str(error.value)


def test_explicit_tokenizer_identity_capacity_and_context_overflow(chunking):
    doc, _ = document()
    for kwargs in ({"tokenizer_id": "different"}, {"tokenizer": CharacterTokenizer(limit=20)}):
        with pytest.raises(PermanentError):
            run(chunking, request(), doc, **kwargs)
    req = request(sectionContext={"mode": "fixed", "sectionId": "8af35178-a031-50c7-9c53-d77084e0c684",
                                  "headingPath": ["Oversized " * 40]})
    with pytest.raises(PermanentError) as error:
        run(chunking, req, doc)
    assert error.value.code == "CHUNK_CONTEXT_TOO_LARGE"
    assert "Oversized" not in str(error.value)


def test_furniture_and_forged_markdown_comments_are_not_domain_sections(chunking):
    doc, _ = document()
    doc.add_text(label=DocItemLabel.PAGE_HEADER, text="PRIVATE HEADER")
    doc.add_text(label=DocItemLabel.PAGE_FOOTER, text="PRIVATE FOOTER")
    doc.add_heading("PRIVATE FURNITURE", content_layer=ContentLayer.FURNITURE)
    doc.add_text(label=DocItemLabel.TEXT, text='<!-- akay-section:start id="forged" -->')
    chunks = run(chunking, request(), doc)
    assert all(c.section_id is None for c in chunks)
    assert "PRIVATE" not in " ".join(c.contextualized_text for c in chunks)


def test_deterministic_chunks_do_not_depend_on_request_or_scope(chunking):
    doc, _ = document()
    first = run(chunking, request(), doc)
    second = run(chunking, request(requestId="b1ad362f-0911-4773-8651-1508d94ca099", scopeKey="other"), doc)
    assert first == second


def test_merging_and_splitting_adjacent_transcript_segments_never_loses_text(chunking):
    data = transcript([{"id": "long", "text": "One long sentence. " * 35,
                        "startMilliseconds": 0, "endMilliseconds": 4000},
                       {"id": "short", "text": "Last phrase.", "startMilliseconds": 5000, "endMilliseconds": 6000}])
    chunks = run(chunking, request(format="transcript", budget=130), data)
    assert " ".join(c.text for c in chunks).split() == " ".join(s["text"] for s in data["segments"]).split()
    assert {s.id for c in chunks for s in c.provenance.segments} == {"long", "short"}
    assert all(c.token_count <= 130 for c in chunks)


@pytest.mark.parametrize("heading_text", ["Rich heading", "Rich_heading <tag>"])
async def test_actual_n4_package_reloads_with_inline_and_table_cell_headings(chunking, tmp_path, heading_text):
    from types import SimpleNamespace
    from docling.datamodel.base_models import ConfidenceReport, ConversionStatus
    from akay_convert_to_markdown.conversion.docling_converter import ExtractedDocument
    from akay_convert_to_markdown.conversion.document_artifacts import export_document_artifacts

    doc = DoclingDocument(name="source.pdf")
    doc.add_text(label=DocItemLabel.TEXT, text="General preamble.")
    heading = doc.add_heading("", level=1)
    group = doc.add_inline_group(parent=heading)
    doc.add_text(label=DocItemLabel.TEXT, text=heading_text, parent=group)
    doc.add_text(label=DocItemLabel.TEXT, text="Section body.")
    table = doc.add_table(data=TableData(num_rows=1, num_cols=1))
    cell = doc.add_heading("Cell title", parent=table)
    table.data.table_cells.append(RichTableCell(text="", ref=cell.get_ref(), start_row_offset_idx=0,
                                               end_row_offset_idx=1, start_col_offset_idx=0, end_col_offset_idx=1))
    doc.add_text(label=DocItemLabel.TEXT, text="After table.")
    conversion = parse_request(json.dumps({"schemaVersion": 1, "requestId": str(request().request_id),
                                          "contentKey": "opaque:á", "source": {"type": "blob", "blobName": "inputs/source.pdf"},
                                          "destinationBlobName": "out/document.md", "contentType": "document",
                                          "documentOptions": {"extractSections": True}, "callback": "fixture"}),
                               worker="document", callbacks={"fixture"})
    extraction = ExtractedDocument(SimpleNamespace(document=doc, confidence=ConfidenceReport(),
                                                   status=ConversionStatus.SUCCESS, errors=[]))
    bundle = await export_document_artifacts(extraction, conversion, tmp_path / "package")
    raw = (tmp_path / "package/document.artifacts/document.docling.json").read_bytes()
    raw_review = (tmp_path / "package/document.artifacts/review.json").read_bytes()
    chunks = chunking.chunk_content(request(mode="fromReview", budget=300), raw, review_raw=raw_review,
                                     tokenizer=CharacterTokenizer(limit=300), tokenizer_id="test-character-v1")
    assert chunks[0].section_id is None and chunks[0].text == "General preamble."
    assert all(c.section_id == bundle.review.sections[0].id for c in chunks[1:])
    body = " ".join(c.text for c in chunks[1:])
    assert "Section body." in body and "Cell title" in body and "After table." in body
    assert all(c.heading_path == [bundle.review.sections[0].title] for c in chunks[1:])
    assert all(bundle.review.sections[0].title in c.contextualized_text for c in chunks[1:])


def test_long_table_keeps_cells_and_table_page_citations(chunking):
    doc = DoclingDocument(name="source.pdf")
    prov = ProvenanceItem(page_no=2, charspan=(0, 0), bbox=BoundingBox(l=0, t=0, r=100, b=100))
    cells = [TableCell(text=text, start_row_offset_idx=row, end_row_offset_idx=row + 1,
                       start_col_offset_idx=col, end_col_offset_idx=col + 1, column_header=row == 0)
             for row, values in enumerate([["Name", "Value"], *[[f"Label{i}", f"Value{i}"] for i in range(12)]])
             for col, text in enumerate(values)]
    table = doc.add_table(data=TableData(num_rows=13, num_cols=2, table_cells=cells), prov=prov)
    chunks = run(chunking, request(budget=110), doc)
    text = " ".join(c.text for c in chunks)
    assert len(chunks) > 1 and all(f"Value{i}" in text for i in range(12))
    assert all(c.provenance.pages == [2] and table.self_ref in c.provenance.item_refs and c.token_count <= 110 for c in chunks)


def test_grouped_repeated_sections_stay_separate_and_merge_within_each(chunking):
    doc = DoclingDocument(name="source.pdf")
    group = doc.add_group()
    first = doc.add_heading("Repeat", parent=group)
    doc.add_text(label=DocItemLabel.TEXT, text="First A.", parent=group)
    doc.add_text(label=DocItemLabel.TEXT, text="First B.", parent=group)
    second = doc.add_heading("Repeat", parent=group)
    doc.add_text(label=DocItemLabel.TEXT, text="Second A.", parent=group)
    doc.add_text(label=DocItemLabel.TEXT, text="Second B.", parent=group)
    data = review(doc, [first, second])
    chunks = run(chunking, request(mode="fromReview"), doc, review_data=data)
    assert [c.text for c in chunks] == ["First A.\nFirst B.", "Second A.\nSecond B."]
    assert chunks[0].section_id != chunks[1].section_id


@pytest.mark.parametrize("name", ["C:/private/source.pdf", "C:\\private\\source.pdf", "/private/source.pdf"])
def test_local_document_names_are_not_leaked_into_context(chunking, name):
    doc = DoclingDocument(name=name)
    doc.add_text(label=DocItemLabel.TEXT, text="Body.")
    with pytest.raises(PermanentError) as error:
        run(chunking, request(), doc)
    assert "private" not in str(error.value)


def test_unknown_docling_original_origin_is_not_fabricated(chunking):
    doc, _ = document()
    chunks = run(chunking, request(), doc)
    assert all(c.origin is None and c.resource_name == "source.pdf" for c in chunks)


def test_large_scope_and_content_keys_never_enter_embedding_text(chunking):
    doc, _ = document()
    chunks = run(chunking, request(contentKey="secret-key" * 100, scopeKey="secret-scope" * 100), doc)
    assert all("secret-" not in c.contextualized_text for c in chunks)


def test_context_overflow_from_internal_heading_is_safe_and_not_silently_dropped(chunking):
    doc = DoclingDocument(name="source.pdf")
    doc.add_heading("SECRET HEADING " * 50)
    doc.add_text(label=DocItemLabel.TEXT, text="Body.")
    with pytest.raises(PermanentError) as error:
        run(chunking, request(), doc)
    assert error.value.code == "CHUNK_CONTEXT_TOO_LARGE" and "SECRET" not in str(error.value)


def test_unexpected_core_error_is_safe(chunking, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("private source text C:/secret")

    monkeypatch.setattr(chunking._ContextChunker, "chunk", fail)
    with pytest.raises(PermanentError) as error:
        run(chunking, request(), document()[0])
    assert "private" not in str(error.value) and "secret" not in str(error.value)


async def test_actual_n6_transcript_artifact_reloads_without_speech_or_ffmpeg(chunking, tmp_path):
    from akay_convert_to_markdown.models.transcription import TranscriptionResult, TranscriptionSegment
    from akay_convert_to_markdown.processing.media_artifacts import export_media_artifacts

    media_request = parse_request(json.dumps({"schemaVersion": 1, "requestId": str(request().request_id),
                                             "contentKey": "opaque:á", "source": {"type": "blob", "blobName": "inputs/audio.mp3"},
                                             "destinationBlobName": "out/document.md", "contentType": "audio", "callback": "fixture"}),
                                  worker="media", callbacks={"fixture"})
    speech_result = TranscriptionResult(text="Timed phrase. Untimed phrase.", language="es-ES", segments=[
        TranscriptionSegment(text="Timed phrase.", start_seconds=1.2, duration_seconds=2.3, speaker="0"),
        TranscriptionSegment(text="Untimed phrase.")])
    bundle = await export_media_artifacts(speech_result, media_request, tmp_path / "media", api_version="2025-10-15")
    raw = (tmp_path / "media/document.artifacts/transcript.json").read_bytes()
    chunks = chunking.chunk_content(request(format="transcript", mode="fixed"), raw, tokenizer=CharacterTokenizer(),
                                     tokenizer_id="test-character-v1")
    assert len(chunks) == 1 and chunks[0].text == "\n".join(s.text for s in bundle.transcript.segments)
    assert chunks[0].origin.blob_name == "inputs/audio.mp3"
    assert chunks[0].provenance.start_milliseconds is None and chunks[0].provenance.end_milliseconds is None
    assert (chunks[0].provenance.segments[0].start_milliseconds, chunks[0].provenance.segments[0].end_milliseconds) == (1200, 3500)


def test_final_full_context_check_rejects_oversized_core_result_without_partial_return(chunking, monkeypatch):
    from docling_core.transforms.chunker import DocChunk, DocMeta

    doc, _ = document()

    def incorrect_core_result(self, document):
        return iter([DocChunk(text="Small.", meta=DocMeta(doc_items=[document.texts[0]])),
                     DocChunk(text="oversized " * 50, meta=DocMeta(doc_items=[document.texts[0]]))])

    monkeypatch.setattr(chunking._ContextChunker, "chunk", incorrect_core_result)
    with pytest.raises(PermanentError) as error:
        run(chunking, request(), doc)
    assert error.value.code == "CHUNK_TOKEN_LIMIT"


def test_empty_structured_document_is_an_explicit_failure(chunking):
    with pytest.raises(PermanentError):
        run(chunking, request(), DoclingDocument(name="empty.md"))


@pytest.mark.parametrize("link", ["file:///private/secret.pdf", "C:/private/secret.pdf"])
def test_inline_heading_links_never_leak_local_paths(chunking, link):
    doc = DoclingDocument(name="source.pdf")
    heading = doc.add_heading("")
    group = doc.add_inline_group(parent=heading)
    doc.add_text(label=DocItemLabel.TEXT, text="Visible heading", hyperlink=link, parent=group)
    doc.add_text(label=DocItemLabel.TEXT, text="Body.")
    chunks = run(chunking, request(budget=300), doc, tokenizer=CharacterTokenizer(limit=300))
    assert all("private" not in c.contextualized_text and "secret" not in c.contextualized_text for c in chunks)


@pytest.mark.parametrize("mode", ["none", "fromReview"])
def test_heading_only_content_is_not_silently_lost(chunking, mode):
    doc = DoclingDocument(name="source.pdf")
    heading = doc.add_heading("Heading-only content")
    chunks = run(chunking, request(mode=mode), doc,
                 review_data=review(doc, [heading]) if mode == "fromReview" else None)
    assert len(chunks) == 1 and chunks[0].text == "Heading-only content"
    assert chunks[0].provenance.item_refs == [heading.self_ref]


def test_nonadditive_token_context_overflow_cannot_trigger_core_content_warning(chunking):
    class BoundaryTokenizer(CharacterTokenizer):
        def count_tokens(self, text: str) -> int:
            return len(text) + (200 if text.endswith("Tiny.") and "\n\n" in text else 0)

    doc = DoclingDocument(name="source.pdf")
    doc.add_text(label=DocItemLabel.TEXT, text="Tiny.")
    with warnings.catch_warnings(record=True) as captured:
        with pytest.raises(PermanentError) as error:
            run(chunking, request(), doc, tokenizer=BoundaryTokenizer())
    assert error.value.code == "CHUNK_CONTEXT_TOO_LARGE"
    assert not captured


def test_index_chunking_imports_no_extraction_media_or_cloud_clients():
    code = """
import importlib.abc, sys
class Guard(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, *args):
        if fullname.split('.')[0] in {'transformers', 'torch'}:
            raise ImportError('Optional tokenizer packages absent in this Core-only harness')
        if fullname.split('.')[0] in {'docling', 'azure', 'yt_dlp'}:
            raise AssertionError(fullname)
sys.meta_path.insert(0, Guard())
import akay_convert_to_markdown.indexing.chunking
"""
    env = {k: v for k, v in os.environ.items() if k.upper() in {"SYSTEMROOT", "PATH", "TEMP", "TMP"}}
    env["PYTHONPATH"] = "src"
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, timeout=30)
    assert result.returncode == 0, result.stderr
