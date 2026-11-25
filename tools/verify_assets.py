"""Verify explicit offline asset inputs against committed N12 locks; never download."""

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]


def verify_file(path, expected):
    with path.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != expected["sha256"]:
            raise ValueError(f"Asset checksum mismatch: {path.name}")
    if "bytes" in expected and path.stat().st_size != expected["bytes"]:
        raise ValueError(f"Asset size mismatch: {path.name}")


def verify_document(directory, lock):
    root = directory.resolve(strict=True)
    for entry in lock["files"]:
        relative = PurePosixPath(entry["path"])
        if relative.is_absolute() or ".." in relative.parts or "\\" in entry["path"] or ":" in entry["path"]:
            raise ValueError("Asset lock paths must be portable and relative.")
        path = (root / relative).resolve(strict=True)
        if not path.is_relative_to(root):
            raise ValueError("An asset resolves outside its supplied directory.")
        verify_file(path, entry)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--document-dir", type=Path)
    parser.add_argument("--tokenizer-file", type=Path)
    args = parser.parse_args()
    if args.document_dir is None and args.tokenizer_file is None:
        parser.error("Supply at least one explicit asset location.")
    if args.document_dir is not None:
        lock = json.loads((ROOT / "requirements/document-models.json").read_text())
        verify_document(args.document_dir, lock)
        print(f"PASS {len(lock['files'])} locked document assets; seven OCR selections share three files")
    if args.tokenizer_file is not None:
        lock = json.loads((ROOT / "requirements/index-tokenizer.json").read_text())
        verify_file(args.tokenizer_file, lock)
        print("PASS locked cl100k_base tokenizer")


if __name__ == "__main__":
    main()
