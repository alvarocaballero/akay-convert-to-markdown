"""Content type detection tests."""

from __future__ import annotations

import pytest

from akay_convert_to_markdown.models.content_type import ContentType, detect_content_type


@pytest.mark.parametrize("name", ["a.pdf", "a.docx", "a.pptx", "a.html", "a.htm", "a.txt", "a.md"])
def test_documents_map_to_document(name):
    assert detect_content_type(file_name=name) is ContentType.DOCUMENT


@pytest.mark.parametrize("name", ["a.mp3", "a.wav", "a.aac", "a.m4a", "a.ogg", "a.opus", "a.flac"])
def test_audio_extensions_map_to_audio(name):
    assert detect_content_type(file_name=name) is ContentType.AUDIO


@pytest.mark.parametrize("name", ["a.mp4", "a.mov", "a.mkv", "a.webm", "a.avi"])
def test_video_extensions_map_to_video(name):
    assert detect_content_type(file_name=name) is ContentType.VIDEO


def test_explicit_type_wins_over_extension():
    assert detect_content_type(file_name="a.mp4", explicit_type="audio") is ContentType.AUDIO


def test_explicit_type_is_case_insensitive():
    assert detect_content_type(file_name="a.pdf", explicit_type="Video") is ContentType.VIDEO


def test_unknown_explicit_type_falls_back_to_extension():
    assert detect_content_type(file_name="a.mp3", explicit_type="unknown") is ContentType.AUDIO


def test_unknown_extension_falls_back_to_document():
    assert detect_content_type(file_name="a.xyz") is ContentType.DOCUMENT


def test_missing_file_name_falls_back_to_document():
    assert detect_content_type(file_name=None) is ContentType.DOCUMENT
