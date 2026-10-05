"""Message validation tests."""

from __future__ import annotations

import json
import uuid

import pytest

from akay_convert_to_markdown.errors.exceptions import InvalidMessageError, UnsupportedDocumentTypeError
from akay_convert_to_markdown.models.conversion_request import (
    parse_conversion_request,
    recover_invalid_message_identity,
    validate_extension,
)


def _message(**overrides) -> str:
    data = {
        "documentId": str(uuid.uuid4()),
        "contextId": str(uuid.uuid4()),
        "userId": str(uuid.uuid4()),
        "fileName": "tema-1.pdf",
        "sourceBlobName": "ctx/doc/tema-1.pdf",
        "callback": "subject-topic",
    }
    data.update(overrides)
    return json.dumps(data)


def test_valid_message_parses():
    request = parse_conversion_request(_message())
    assert request.document_id is not None
    assert request.file_name == "tema-1.pdf"


def test_missing_document_id_is_invalid():
    data = json.loads(_message())
    del data["documentId"]
    with pytest.raises(InvalidMessageError):
        parse_conversion_request(json.dumps(data))


def test_missing_source_blob_name_is_invalid():
    data = json.loads(_message())
    del data["sourceBlobName"]
    with pytest.raises(InvalidMessageError):
        parse_conversion_request(json.dumps(data))


def test_missing_callback_is_invalid():
    data = json.loads(_message())
    del data["callback"]
    with pytest.raises(InvalidMessageError):
        parse_conversion_request(json.dumps(data))


def test_invalid_json_is_invalid():
    with pytest.raises(InvalidMessageError):
        parse_conversion_request("{not-json")


def test_invalid_uuid_is_invalid():
    with pytest.raises(InvalidMessageError):
        parse_conversion_request(_message(documentId="not-a-uuid"))


def test_numeric_ids_are_valid():
    request = parse_conversion_request(_message(documentId=1, contextId=2, userId=3))

    assert request.document_id == 1
    assert request.context_id == 2
    assert request.user_id == 3


def test_mixed_int_and_uuid_ids_are_valid():
    context_id = str(uuid.uuid4())
    request = parse_conversion_request(_message(documentId=1, contextId=context_id, userId=3))

    assert request.document_id == 1
    assert str(request.context_id) == context_id
    assert request.user_id == 3


def test_arbitrary_string_id_is_invalid():
    with pytest.raises(InvalidMessageError):
        parse_conversion_request(_message(documentId="../.."))


def test_unsupported_extension_rejected():
    with pytest.raises(UnsupportedDocumentTypeError):
        validate_extension("tema-1.xyz")


@pytest.mark.parametrize("name", ["a.pdf", "a.docx", "a.pptx", "a.html", "a.htm", "a.PDF"])
def test_supported_extensions_accepted(name):
    assert validate_extension(name) in {".pdf", ".docx", ".pptx", ".html", ".htm"}


def test_recover_identity_returns_present_fields():
    document_id = str(uuid.uuid4())
    context_id = str(uuid.uuid4())
    raw = json.dumps({"documentId": document_id, "contextId": context_id})

    identity = recover_invalid_message_identity(raw)

    assert identity is not None
    assert identity["documentId"] == document_id
    assert identity["contextId"] == context_id
    assert "userId" not in identity
    assert "fileName" not in identity
    assert "callback" not in identity


def test_recover_identity_recovers_callback():
    document_id = str(uuid.uuid4())
    raw = json.dumps({"documentId": document_id, "callback": "student-document"})

    identity = recover_invalid_message_identity(raw)

    assert identity is not None
    assert identity["callback"] == "student-document"


def test_recover_identity_none_without_document_id():
    raw = json.dumps({"contextId": str(uuid.uuid4())})
    assert recover_invalid_message_identity(raw) is None


def test_recover_identity_none_with_invalid_document_id():
    raw = json.dumps({"documentId": "not-a-uuid"})
    assert recover_invalid_message_identity(raw) is None


def test_recover_identity_none_for_invalid_json():
    assert recover_invalid_message_identity("{bad") is None


def test_recover_identity_recovers_numeric_ids_preserving_type():
    raw = json.dumps({"documentId": 123, "contextId": 456, "userId": 789})

    identity = recover_invalid_message_identity(raw)

    assert identity is not None
    assert identity["documentId"] == 123
    assert identity["contextId"] == 456
    assert identity["userId"] == 789
    assert isinstance(identity["documentId"], int)


def test_recover_identity_mixed_types():
    context_id = str(uuid.uuid4())
    raw = json.dumps({"documentId": 123, "contextId": context_id})

    identity = recover_invalid_message_identity(raw)

    assert identity is not None
    assert identity["documentId"] == 123
    assert identity["contextId"] == context_id


def test_recover_identity_none_with_path_traversal_document_id():
    raw = json.dumps({"documentId": "../.."})
    assert recover_invalid_message_identity(raw) is None


def test_recover_identity_none_with_boolean_document_id():
    raw = json.dumps({"documentId": True})
    assert recover_invalid_message_identity(raw) is None
