"""Temporary filename hardening tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from akay_convert_to_markdown.processing.document_processor import safe_source_filename


@pytest.mark.parametrize(
    ("file_name", "expected"),
    [
        ("tema-1.pdf", "tema-1.pdf"),
        ("sub/dir/tema-1.pdf", "tema-1.pdf"),
        ("..\\..\\tema-1.pdf", "tema-1.pdf"),
        ("/absolute/path/tema-1.pdf", "tema-1.pdf"),
        ("C:\\Windows\\tema-1.pdf", "tema-1.pdf"),
        ("..", "source"),
        (".", "source"),
        ("", "source"),
        ("/", "source"),
        ("../../", "source"),
    ],
)
def test_safe_source_filename(file_name, expected):
    assert safe_source_filename(file_name) == expected


@pytest.mark.parametrize(
    "file_name",
    [
        "..",
        ".",
        "/etc/passwd.pdf",
        "..\\..\\windows\\system32\\evil.pdf",
        "a/b/../../secret.pdf",
    ],
)
def test_safe_source_filename_stays_within_temp_dir(file_name, tmp_path):
    temp_dir = tmp_path / "doc"
    temp_dir.mkdir()
    source_path = temp_dir / safe_source_filename(file_name)

    assert source_path.parent == temp_dir
    assert safe_source_filename(file_name) not in ("", ".", "..")
    assert not safe_source_filename(file_name).startswith("/")
    assert "\\" not in safe_source_filename(file_name)
