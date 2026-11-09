"""Service Bus request validation and recovery tests."""
import json
from uuid import uuid4

import pytest

from akay_convert_to_markdown.errors.exceptions import InvalidMessageError, UnsupportedDocumentTypeError
from akay_convert_to_markdown.models.conversion_request import parse_conversion_request, recover_invalid_message_identity, validate_extension


def message(**overrides):
    data = {"requestId": str(uuid4()), "source": {"type": "blob", "blobName": "path/a.pdf"},
            "destinationBlobName": "out/a.md", "callback": "topic-content"}
    data.update(overrides)
    return json.dumps(data)


def test_valid_message_defaults():
    request = parse_conversion_request(message())
    assert request.file_name == "a.pdf"
    assert request.overwrite_destination is False
    assert request.payload == {}


@pytest.mark.parametrize("overrides", [
    {"requestId": "invalid"}, {"source": {"type": "youtube", "url": "https://example.com"}},
    {"source": {"type": "blob", "blobName": ""}}, {"destinationBlobName": ""},
    {"overwriteDestination": "false"}, {"payload": []}, {"callback": ""},
])
def test_invalid_message(overrides):
    with pytest.raises(InvalidMessageError):
        parse_conversion_request(message(**overrides))


def test_invalid_json_and_bytes():
    for raw in ("{bad", b"\xff", "[]"):
        with pytest.raises(InvalidMessageError):
            parse_conversion_request(raw)


def test_recover_identity_and_payload():
    request_id = str(uuid4())
    raw = message(requestId=request_id, payload={"nested": [1, None]})
    identity = recover_invalid_message_identity(raw)
    assert identity["requestId"] == request_id
    assert identity["payload"] == {"nested": [1, None]}
    assert identity["callback"] == "topic-content"


@pytest.mark.parametrize("raw", ['{bad', '[]', '{}', '{"requestId": "../.."}', b'\xff'])
def test_unrecoverable_identity(raw):
    assert recover_invalid_message_identity(raw) is None


@pytest.mark.parametrize("name", ["a.pdf", "a.docx", "a.pptx", "a.html", "a.htm", "a.txt", "a.md", "a.PDF"])
def test_supported_extensions(name):
    assert validate_extension(name) == name[name.rfind('.'):].lower()


def test_unsupported_extension():
    with pytest.raises(UnsupportedDocumentTypeError):
        validate_extension("a.xyz")
