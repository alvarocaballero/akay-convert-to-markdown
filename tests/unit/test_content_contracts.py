"""N2 wire contracts and ordering decisions, without extraction or live services."""

from __future__ import annotations

from copy import deepcopy
import importlib
import json
from pathlib import Path
import re

import pytest
from pydantic import ValidationError

from akay_convert_to_markdown.errors.exceptions import InvalidMessageError
from akay_convert_to_markdown.models.conversion_request import parse_conversion_request


FIXTURES = Path(__file__).parents[1] / "fixtures" / "content_processing" / "contracts.json"
CALLBACKS = {"fixture-result", "topic-content", "content-index-result"}


@pytest.fixture
def contracts():
    return importlib.import_module("akay_convert_to_markdown.contracts")


@pytest.fixture
def examples():
    return json.loads(FIXTURES.read_text(encoding="utf-8"))


def parse(contracts, data, worker):
    return contracts.parse_request(json.dumps(data), worker=worker, callbacks=CALLBACKS)


@pytest.mark.parametrize("variant,worker,model", [
    ("document", "document", "DocumentRequest"), ("media", "media", "MediaRequest"),
    ("index", "index", "IndexRequest"), ("delete", "index", "DeleteRequest"),
])
def test_valid_envelopes_round_trip_and_keep_opaque_payload(contracts, examples, variant, worker, model):
    request = parse(contracts, examples[variant], worker)
    assert isinstance(request, getattr(contracts, model))
    wire = request.model_dump(mode="json", by_alias=True)
    assert wire["payload"] == examples[variant]["payload"]
    assert wire["contentKey"] == examples[variant]["contentKey"]
    assert parse(contracts, wire, worker) == request
    with pytest.raises(ValidationError):
        request.content_key = "changed"


@pytest.mark.parametrize("extract,code,formula", [(e, c, f) for e in (False, True)
                                                 for c in (False, True) for f in (False, True)])
def test_document_flags_independent_and_default_false(contracts, examples, extract, code, formula):
    data = examples["document"]
    data.pop("documentOptions")
    default = parse(contracts, data, "document")
    assert default.document_options.model_dump() == {
        "extract_sections": False, "code_enrichment": False, "formula_enrichment": False, "ocr_language": "es",
    }
    data["documentOptions"] = {"extractSections": extract, "codeEnrichment": code, "formulaEnrichment": formula}
    options = parse(contracts, data, "document").document_options
    assert (options.extract_sections, options.code_enrichment, options.formula_enrichment) == (extract, code, formula)


@pytest.mark.parametrize("language", ["es", "eu", "gl", "ca", "fr", "en", "de"])
def test_document_ocr_language_round_trips_and_changes_effective_identity(contracts, examples, language):
    data = examples["document"]
    data["documentOptions"].pop("ocrLanguage")
    default = parse(contracts, data, "document")
    assert default.document_options.ocr_language == "es"
    data["documentOptions"]["ocrLanguage"] = language
    selected = parse(contracts, data, "document")
    assert selected.document_options.ocr_language == language
    wire = selected.model_dump(mode="json", by_alias=True)
    assert wire["documentOptions"]["ocrLanguage"] == language
    assert parse(contracts, wire, "document") == selected
    assert (contracts.RequestIdentity.capture(default).canonical_request ==
            contracts.RequestIdentity.capture(selected).canonical_request) is (language == "es")


@pytest.mark.parametrize("value", [None, "", " ", "ES", "es-ES", "iso:es", "it", 1, True, ["es"], {"lang": "es"}])
def test_document_ocr_language_rejects_invalid_values(contracts, examples, value):
    examples["document"]["documentOptions"]["ocrLanguage"] = value
    with pytest.raises(InvalidMessageError):
        parse(contracts, examples["document"], "document")


def test_empty_document_options_default_to_spanish(contracts, examples):
    examples["document"]["documentOptions"] = {}
    assert parse(contracts, examples["document"], "document").document_options.ocr_language == "es"


@pytest.mark.parametrize("field,value", [
    ("schemaVersion", True), ("schemaVersion", "1"), ("schemaVersion", 2),
    ("requestId", 42), ("requestId", "not-a-uuid"), ("contentKey", ""),
    ("contentKey", "   "), ("contentKey", 7), ("overwriteDestination", "false"),
    ("overwriteDestination", 0), ("callback", "https://untrusted.invalid"),
    ("callback", "unknown"), ("payload", []), ("payload", {"nested": float("nan")}),
    ("payload", {"nested": [float("inf")]}), ("documentOptions", {"formulaEnrichment": 1}),
    ("documentOptions", {"codeEnrichment": "true"}), ("documentOptions", {"unknown": False}),
    ("source", {"type": "youtube", "url": "https://www.youtube.com/watch?v=abcdefghijk"}),
    ("source", {"type": "blob", "blobName": "x", "url": "https://untrusted.invalid"}),
    ("contentType", "audio"), ("unexpected", True),
])
def test_invalid_document_fields_fail_safely(contracts, examples, field, value):
    examples["document"][field] = value
    with pytest.raises(InvalidMessageError, match="invalid") as error:
        parse(contracts, examples["document"], "document")
    assert "untrusted" not in str(error.value)


@pytest.mark.parametrize("destination", ["/local.md", "C:/local.md", "a\\b.md", "a/../b.md",
                                        "a//b.md", "a/./b.md", "x.txt", "x.artifacts/file.md",
                                        "https://example.invalid/a.md", "x.md?sig=secret", "x.md#fragment"])
def test_destination_is_a_portable_markdown_blob_not_a_path_or_url(contracts, examples, destination):
    examples["document"]["destinationBlobName"] = destination
    with pytest.raises(InvalidMessageError):
        parse(contracts, examples["document"], "document")


@pytest.mark.parametrize("content_type,source", [
    ("audio", {"type": "blob", "blobName": "uploads/audio.mp3"}),
    ("video", {"type": "blob", "blobName": "uploads/audio.webm"}),
    ("video", {"type": "youtube", "url": "https://www.youtube.com/watch?v=abcdefghijk"}),
])
def test_media_variants(contracts, examples, content_type, source):
    data = dict(examples["media"], contentType=content_type, source=source)
    assert parse(contracts, data, "media").source.model_dump(by_alias=True) == source


@pytest.mark.parametrize("change", [
    {"contentType": "document"}, {"contentType": "audio", "source": {"type": "youtube", "url": "https://www.youtube.com/watch?v=abcdefghijk"}},
    {"documentOptions": {}}, {"source": {"type": "url", "url": "https://external.invalid"}},
    {"source": {"type": "youtube", "url": "file:///local"}},
    {"source": {"type": "youtube", "url": "https://external.invalid/video"}},
])
def test_invalid_media_combinations(contracts, examples, change):
    with pytest.raises(InvalidMessageError):
        parse(contracts, dict(examples["media"], **change), "media")


@pytest.mark.parametrize("mode", ["fixed", "fromReview", "none"])
@pytest.mark.parametrize("source_format", ["docling", "transcript"])
def test_index_source_and_section_modes(contracts, examples, mode, source_format):
    data = examples["index"]
    data["source"]["format"] = source_format
    if mode == "fromReview":
        data["sectionContext"] = {"mode": mode, "reviewBlobName": "output/document.artifacts/review.json"}
    elif mode == "none":
        data["sectionContext"] = {"mode": mode}
    if mode == "fromReview" and source_format == "transcript":
        with pytest.raises(InvalidMessageError):
            parse(contracts, data, "index")
    else:
        assert parse(contracts, data, "index").section_context.mode == mode


@pytest.mark.parametrize("field,value", [("operationSequence", 0), ("operationSequence", -1),
                                        ("operationSequence", True), ("operationSequence", "1"),
                                        ("scopeKey", ""), ("operation", "reassign"),
                                        ("source", {"type": "youtube", "url": "https://youtu.be/abcdefghijk"}),
                                        ("sectionContext", {"mode": "fixed"})])
def test_invalid_index_envelopes(contracts, examples, field, value):
    examples["index"][field] = value
    with pytest.raises(InvalidMessageError):
        parse(contracts, examples["index"], "index")


@pytest.mark.parametrize("field,value", [("dimensions", 0), ("dimensions", "3"), ("maxChunkTokens", True),
                                        ("maxChunkTokens", 0), ("distance", "anything"),
                                        ("tokenizer", ""), ("endpoint", "https://external.invalid"),
                                        ("apiKey", "secret")])
def test_profile_is_an_explicit_validated_snapshot_without_secrets(contracts, examples, field, value):
    examples["index"]["indexProfile"][field] = value
    with pytest.raises(InvalidMessageError):
        parse(contracts, examples["index"], "index")


@pytest.mark.parametrize("reserved", ["scopeKey", "contentKey", "profileId", "operationSequence", "chunkIndex",
                                     "sectionId", "headingPath", "text", "contextualizedText", "source", "provenance", "metadata"])
def test_metadata_cannot_override_reserved_index_fields(contracts, examples, reserved):
    examples["index"]["metadata"][reserved] = "override"
    with pytest.raises(InvalidMessageError):
        parse(contracts, examples["index"], "index")


@pytest.mark.parametrize("change", [{"source": {}}, {"indexProfile": {}}, {"indexTarget": {"profileId": "", "collection": "x"}},
                                   {"scopeKey": ""}, {"contentKey": ""}, {"operationSequence": 0}])
def test_delete_requires_an_exact_nonempty_target(contracts, examples, change):
    with pytest.raises(InvalidMessageError):
        parse(contracts, dict(examples["delete"], **change), "index")


def test_completed_events_have_exact_artifact_variants_and_payload(contracts, examples):
    for variant, worker in (("document", "document"), ("media", "media")):
        request = parse(contracts, examples[variant], worker)
        layout = contracts.ArtifactLayout.for_destination(request.destination_blob_name)
        refs = layout.document_refs() if variant == "document" else layout.media_refs()
        event = contracts.conversion_completed(request, refs)
        wire = event.model_dump(mode="json", by_alias=True)
        assert wire["eventType"] == "document.conversion.completed"
        assert wire["payload"] == examples[variant]["payload"]
        assert wire["schemaVersion"] == 1
        assert set(wire["artifacts"]) == ({"doclingJsonBlobName", "reviewBlobName"} if variant == "document"
                                          else {"transcriptJsonBlobName", "reviewBlobName"})
        contracts.parse_event(json.dumps(wire))
        wire["images"] = []
        with pytest.raises(InvalidMessageError):
            contracts.parse_event(json.dumps(wire))
        wire.pop("images")
        wire["artifacts"]["imagesPrefix"] = "output/images/"
        with pytest.raises(InvalidMessageError):
            contracts.parse_event(json.dumps(wire))


@pytest.mark.parametrize("destination,prefix", [("topics/document.md", "topics/document.artifacts"),
                                               ("topics/notes.md", "topics/notes.artifacts"),
                                               ("manual.v2.md", "manual.v2.artifacts")])
def test_artifact_layout_avoids_shared_parent_collisions(contracts, destination, prefix):
    layout = contracts.ArtifactLayout.for_destination(destination)
    assert layout.document_refs().review_blob_name == f"{prefix}/review.json"
    assert layout.document_refs().docling_json_blob_name == f"{prefix}/document.docling.json"
    assert layout.media_refs().transcript_json_blob_name == f"{prefix}/transcript.json"


def test_completed_cannot_claim_wrong_content_or_destination_artifacts(contracts, examples):
    request = parse(contracts, examples["document"], "document")
    layout = contracts.ArtifactLayout.for_destination("other.md")
    with pytest.raises(ValueError):
        contracts.conversion_completed(request, layout.document_refs())
    with pytest.raises(ValueError):
        contracts.conversion_completed(request, contracts.ArtifactLayout.for_destination(request.destination_blob_name).media_refs())


def test_review_and_transcript_accept_absent_and_null_measurements(contracts, examples):
    review = contracts.Review.model_validate_json(json.dumps(examples["review"]))
    assert review.confidence.pages[0].layout_score is None
    assert review.confidence.mean_grade is None
    transcript = contracts.Transcript.model_validate_json(json.dumps(examples["transcript"]))
    assert transcript.segments[1].start_milliseconds is None
    for segment in examples["transcript"]["segments"]:
        segment.pop("startMilliseconds")
        segment.pop("endMilliseconds")
    assert contracts.Transcript.model_validate_json(json.dumps(examples["transcript"])).segments[0].end_milliseconds is None


@pytest.mark.parametrize("mutation", ["nan", "infinity", "reversed-time", "negative-time", "beyond-duration", "duplicate-id", "unordered"])
def test_transcript_rejects_invalid_times_or_nonfinite_json(contracts, examples, mutation):
    data = examples["transcript"]
    first = data["segments"][0]
    if mutation == "nan":
        first["startMilliseconds"] = float("nan")
    elif mutation == "infinity":
        data["durationMilliseconds"] = float("inf")
    elif mutation == "reversed-time":
        first["endMilliseconds"] = 1
    elif mutation == "negative-time":
        first["startMilliseconds"] = -1
    elif mutation == "beyond-duration":
        first["endMilliseconds"] = 19000
    elif mutation == "duplicate-id":
        data["segments"][1]["id"] = first["id"]
    else:
        data["segments"][1].update(startMilliseconds=100, endMilliseconds=200)
    with pytest.raises(ValidationError):
        contracts.Transcript.model_validate_json(json.dumps(data))


def test_review_image_inventory_and_media_constraints(contracts, examples):
    data = examples["review"]
    data["confidence"]["pages"][0]["layoutScore"] = float("nan")
    with pytest.raises(ValidationError):
        contracts.Review.model_validate_json(json.dumps(data))
    data["confidence"]["pages"][0]["layoutScore"] = None
    data["images"][0]["blobName"] = "file:///private/local.png"
    with pytest.raises(ValidationError):
        contracts.Review.model_validate_json(json.dumps(data))
    data["images"][0]["blobName"] = "output/document.artifacts/images/figure-001.png"
    data["contentType"] = "audio"
    with pytest.raises(ValidationError):
        contracts.Review.model_validate_json(json.dumps(data))


def test_artifact_result_models_preserve_typed_reviews_and_source_identity(contracts, examples):
    review = examples["review"]
    refs = contracts.ArtifactLayout.for_destination("output/document.md").document_refs()
    result = contracts.DocumentArtifactResult(markdown="# Safety", docling_json={"name": "fixture", "texts": []},
                                              review=contracts.Review.model_validate_json(json.dumps(review)), artifacts=refs)
    assert result.review.images[0].id == "figure-001"
    media_review = dict(review, contentKey="manual:media", contentType="video", source=examples["media"]["source"],
                        sections=[], tables=[], images=[], confidence={},
                        summary={"sectionCount": 0, "tableCount": 0, "imageCount": 0},
                        processing={"engine": "azure-speech", "engineVersion": "fixture"})
    transcript = contracts.Transcript.model_validate_json(json.dumps(examples["transcript"]))
    kwargs = dict(markdown="Disconnect the power.\n\nKeep the manual.", transcript=transcript,
                  review=contracts.Review.model_validate_json(json.dumps(media_review)),
                  artifacts=contracts.ArtifactLayout.for_destination("output/transcript.md").media_refs())
    assert contracts.MediaArtifactResult(**kwargs).transcript == transcript
    media_review["contentKey"] = "different"
    kwargs["review"] = contracts.Review.model_validate_json(json.dumps(media_review))
    with pytest.raises(ValidationError):
        contracts.MediaArtifactResult(**kwargs)


def test_result_events_cover_index_delete_superseded_and_failure_variants(contracts, examples):
    for variant, event_type in (("index", "content.indexing.completed"), ("delete", "content.index.deleted")):
        request = parse(contracts, examples[variant], "index")
        event = contracts.index_completed(request, chunk_count=2 if variant == "index" else None)
        wire = event.model_dump(mode="json", by_alias=True)
        assert wire["eventType"] == event_type
        assert wire["operationSequence"] == examples[variant]["operationSequence"]
        assert wire["index"] == ({"profileId": "fixture-only", "chunkCount": 2} if variant == "index"
                                  else {"profileId": "fixture-only"})
        assert contracts.parse_event(json.dumps(wire)) == event
    request = parse(contracts, examples["index"], "index")
    superseded = contracts.index_superseded(request, current_operation_sequence=2)
    assert contracts.parse_event(superseded.model_dump_json(by_alias=True)) == superseded
    with pytest.raises(ValueError):
        contracts.index_superseded(request, current_operation_sequence=1)
    for variant, worker, event_type in (("document", "document", "document.conversion.failed"),
                                        ("media", "media", "document.conversion.failed"),
                                        ("index", "index", "content.indexing.failed"),
                                        ("delete", "index", "content.index.deletion.failed")):
        request = parse(contracts, examples[variant], worker)
        event = contracts.request_failed(request, code="INVALID_MESSAGE", message="The request is invalid.")
        assert event.event_type == event_type
        assert contracts.parse_event(event.model_dump_json(by_alias=True)) == event
        assert event.payload == request.payload
    assert contracts.idempotency_key(superseded) == f"{superseded.request_id}:content.index.operation.superseded"


def test_ordering_contract_uses_persisted_snapshot_across_profile_changes(contracts, examples):
    index = parse(contracts, examples["index"], "index")
    snapshot = contracts.RequestIdentity.capture(index)
    admitted = contracts.IndexReceipt(identity=snapshot, status="admitted")
    completed = contracts.IndexReceipt(identity=snapshot, status="completed")
    assert contracts.index_admission(index, None) == "admit"
    assert contracts.index_admission(index, admitted) == "resume"
    assert contracts.index_admission(index, completed) == "replay"
    # A persisted representation, not object identity or an in-memory lock.
    restored = contracts.IndexReceipt.model_validate_json(completed.model_dump_json(by_alias=True))
    assert contracts.index_admission(index, restored) == "replay"
    changed = deepcopy(examples["index"])
    changed["indexProfile"]["collection"] = "other-collection"
    assert contracts.index_admission(parse(contracts, changed, "index"), restored) == "conflict"
    changed = deepcopy(examples["index"])
    changed["requestId"] = examples["delete"]["requestId"]
    assert contracts.index_admission(parse(contracts, changed, "index"), restored) == "conflict"
    delete = parse(contracts, examples["delete"], "index")
    assert contracts.index_admission(delete, restored) == "admit"
    deleted = contracts.IndexReceipt(identity=contracts.RequestIdentity.capture(delete), status="completed",
                                      previous_requests=[snapshot])
    assert contracts.index_admission(index, deleted) == "superseded"
    changed["operationSequence"] = 3
    changed["requestId"] = examples["index"]["requestId"]
    assert contracts.index_admission(parse(contracts, changed, "index"), deleted) == "conflict"
    changed["requestId"] = "b1ad362f-0911-4773-8651-1508d94ca005"
    assert contracts.index_admission(parse(contracts, changed, "index"), deleted) == "admit"
    changed["scopeKey"] = "another-scope"
    with pytest.raises(ValueError):
        contracts.index_admission(parse(contracts, changed, "index"), deleted)
    index.payload["nested"] = {"changed": True}
    assert snapshot.canonical_request != contracts.RequestIdentity.capture(index).canonical_request


def test_all_complete_specification_json_examples_validate(contracts):
    spec = (Path(__file__).parents[2] / "docs" / "content-processing-specification.md").read_text(encoding="utf-8")
    validated = 0
    for block in re.findall(r"~~~json\s*\n(.*?)\n~~~", spec, re.DOTALL):
        data = json.loads(block, parse_constant=lambda value: pytest.fail(f"Nonfinite JSON: {value}"))
        if "schemaVersion" not in data:
            continue
        if "eventType" in data:
            contracts.parse_event(block)
        elif "requestId" in data:
            worker = "index" if data.get("operation") in {"index", "delete"} else ("document" if data["contentType"] == "document" else "media")
            contracts.parse_request(block, worker=worker, callbacks=CALLBACKS)
        elif "segments" in data:
            contracts.Transcript.model_validate_json(block)
        else:
            contracts.Review.model_validate_json(block)
        validated += 1
    assert validated == 11


@pytest.mark.parametrize("variant,wrong_worker", [("document", "media"), ("media", "document"),
                                                 ("index", "document"), ("delete", "media")])
def test_contract_cannot_cross_worker_routes(contracts, examples, variant, wrong_worker):
    with pytest.raises(InvalidMessageError):
        parse(contracts, examples[variant], wrong_worker)


@pytest.mark.parametrize("raw", ["[]", "null", "42", "{bad", b"\xff", '{"schemaVersion":1,"schemaVersion":2}'])
def test_malformed_json_is_an_invalid_message(contracts, raw):
    with pytest.raises(InvalidMessageError):
        contracts.parse_request(raw, worker="document", callbacks=CALLBACKS)


def test_duplicate_json_keys_do_not_change_payload_identity(contracts, examples):
    raw = json.dumps(examples["document"]).replace('"payload": {', '"payload": {"duplicate":1,"duplicate":2,')
    with pytest.raises(InvalidMessageError):
        contracts.parse_request(raw, worker="document", callbacks=CALLBACKS)


@pytest.mark.parametrize("variant,parser", [("review", "parse_review"), ("transcript", "parse_transcript")])
def test_artifact_read_boundary_rejects_duplicate_keys(contracts, examples, variant, parser):
    raw = json.dumps(examples[variant])
    parsed = getattr(contracts, parser)(raw)
    assert parsed.content_key == examples[variant]["contentKey"]
    raw = raw.replace('"schemaVersion": 1', '"schemaVersion": 1, "schemaVersion": 1')
    with pytest.raises(InvalidMessageError):
        getattr(contracts, parser)(raw)


def test_partial_failed_events_keep_only_recoverable_typed_identities(contracts, examples):
    for event_type in ("document.conversion.failed", "content.indexing.failed", "content.index.deletion.failed"):
        data = {"schemaVersion": 1, "eventType": event_type, "requestId": examples["document"]["requestId"],
                "error": {"code": "INVALID_MESSAGE", "message": "The request is invalid."}}
        event = contracts.parse_event(json.dumps(data))
        assert event.content_key is None
        assert "callback" not in event.model_dump(by_alias=True)
        data["error"]["stackTrace"] = "private path"
        with pytest.raises(InvalidMessageError):
            contracts.parse_event(json.dumps(data))


def test_receipt_rejects_tampering_and_remembers_old_sequence_conflicts(contracts, examples):
    index = parse(contracts, examples["index"], "index")
    identity = contracts.RequestIdentity.capture(index)
    deleted = contracts.IndexReceipt(identity=contracts.RequestIdentity.capture(parse(contracts, examples["delete"], "index")),
                                      previous_requests=[identity], status="completed")
    conflicting = dict(examples["index"], requestId="b1ad362f-0911-4773-8651-1508d94ca006")
    assert contracts.index_admission(parse(contracts, conflicting, "index"), deleted) == "conflict"
    wire = deleted.model_dump(mode="json", by_alias=True)
    wire["identity"]["requestId"] = examples["index"]["requestId"]
    with pytest.raises(ValidationError):
        contracts.IndexReceipt.model_validate_json(json.dumps(wire))
    wire = deleted.model_dump(mode="json", by_alias=True)
    wire["previousRequests"].append(wire["previousRequests"][0])
    with pytest.raises(ValidationError):
        contracts.IndexReceipt.model_validate_json(json.dumps(wire))


@pytest.mark.parametrize("variant", ["document", "media", "index", "delete"])
async def test_current_consumer_never_processes_versioned_jobs(settings, examples, variant):
    from tests.unit.test_consumer import FakeMessage, FakeReceiver, StubProcessor, _make_consumer

    processor = StubProcessor()
    receiver = FakeReceiver()
    consumer = _make_consumer(settings, processor)
    await consumer._handle_message(receiver, FakeMessage(json.dumps(examples[variant])))
    assert processor.requests == []
    assert len(processor.invalid_notifications) == 1
    assert receiver.completed and not receiver.abandoned


@pytest.mark.parametrize("new_field,value", [("schemaVersion", 1), ("contentKey", "manual:1"),
                                          ("documentOptions", {"extractSections": True}), ("operation", "index"),
                                          ("schema_version", 1), ("content_key", "manual:1"),
                                          ("document_options", {}), ("operation_sequence", 1),
                                          ("scope_key", "manuals:washer")])
def test_legacy_runtime_cannot_silently_ignore_new_contract(new_field, value):
    legacy = {"requestId": "b1ad362f-0911-4773-8651-1508d94ca001",
              "source": {"type": "blob", "blobName": "uploads/lesson.pdf"},
              "destinationBlobName": "output/document.md", "callback": "fixture-result", new_field: value}
    with pytest.raises(InvalidMessageError):
        parse_conversion_request(json.dumps(legacy))
