"""N12 installation boundaries; behavioral checks also run in clean target venvs."""

import importlib.util
import hashlib
import json
from pathlib import Path
import tomllib
from urllib.parse import unquote

import pytest
from packaging.requirements import Requirement


ROOT = Path(__file__).resolve().parents[2]


def test_shared_install_does_not_pull_worker_engines():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    names = {Requirement(value).name for value in project["dependencies"]}
    assert names == {"azure-identity", "azure-servicebus", "azure-storage-blob", "httpx",
                     "pydantic", "pydantic-settings"}
    extras = project["optional-dependencies"]
    assert {"document", "media", "index", "test"} <= extras.keys()
    assert "docling-slim" in {Requirement(value).name for value in extras["document"]}
    assert "docling-core" in {Requirement(value).name for value in extras["index"]}
    assert "yt-dlp" in {Requirement(value).name for value in extras["media"]}


def test_retired_converter_is_not_shipped():
    assert importlib.util.find_spec("akay_convert_to_markdown.conversion.markitdown_converter") is None


@pytest.mark.parametrize("platform", ["windows", "linux"])
@pytest.mark.parametrize("target", ["document", "media", "index"])
def test_resolved_target_locks_exclude_foreign_engines(target, platform):
    path = ROOT / "requirements" / f"{target}-{platform}.txt"
    assert path.is_file(), f"Missing resolved lock: {path.name}"
    requirements = path.read_text()
    pins = {Requirement(line.rstrip(" \\")).name.lower(): line
            for line in requirements.splitlines() if line and line[0].isalnum()}
    assert "--hash=sha256:" in requirements
    assert all("==" in line or " @ https://" in line for line in pins.values())
    assert not any("whisper" in name or name.startswith(("nvidia-", "cuda-")) or
                   name in {"markitdown", "onnxruntime-gpu", "triton", "open-clip-torch", "peft"}
                   for name in pins)
    if target == "document":
        assert {"docling-slim", "rapidocr", "onnxruntime", "torch", "transformers"} <= pins.keys()
        assert not {"qdrant-client", "yt-dlp", "deno"} & pins.keys()
        assert "+cpu" in unquote(pins["torch"])
    elif target == "media":
        assert {"yt-dlp", "yt-dlp-ejs", "deno"} <= pins.keys()
        assert not {"docling", "docling-slim", "docling-core", "torch", "qdrant-client"} & pins.keys()
    else:
        assert {"docling-core", "semchunk", "tiktoken", "qdrant-client"} <= pins.keys()
        assert not {"docling", "docling-slim", "torch", "transformers", "onnxruntime", "yt-dlp", "deno"} & pins.keys()


def test_resource_lock_covers_only_selected_models_and_shared_ocr():
    lock = json.loads((ROOT / "requirements" / "document-models.json").read_text())
    assert lock["pins"]["docling-slim"] == "2.141.0"
    assert set(lock["languages"]) == {"es", "eu", "gl", "ca", "fr", "en", "de"}
    resources = {entry["path"] for entry in lock["files"]}
    assert len(resources) == len(lock["files"]) == 19
    for language, selection in lock["languages"].items():
        assert selection["recognizer"] == language
        assert len(selection["resources"]) == 3
        assert set(selection["resources"]) <= resources
    assert len({path for value in lock["languages"].values() for path in value["resources"]}) == 3
    for entry in lock["files"]:
        assert len(entry["sha256"]) == 64 and entry["bytes"] > 0
        assert "source" not in entry  # No machine-specific audit/cache paths in the lock.
        assert entry["path"].startswith(("RapidOcr/", "docling-project--docling-layout-heron/",
                                         "docling-project--docling-models/model_artifacts/tableformer/accurate/",
                                         "docling-project--CodeFormulaV2/"))


@pytest.mark.parametrize("operation", ["convert", "rebuildFromMarkdown"])
async def test_artifact_engine_version_comes_from_slim_distribution(monkeypatch, tmp_path, operation):
    from importlib.metadata import PackageNotFoundError, version
    from akay_convert_to_markdown.conversion import document_artifacts, markdown_rebuild
    from tests.unit.test_artifact_publication import request as base_request
    from tests.unit.test_reviewed_content import rebuild_request, original_review

    def installed(name):
        if name == "docling":
            raise PackageNotFoundError(name)
        return version(name)

    monkeypatch.setattr(document_artifacts, "version", installed)
    monkeypatch.setattr(markdown_rebuild, "version", installed)
    request = base_request() if operation == "convert" else rebuild_request()
    if operation == "convert":
        from akay_convert_to_markdown.conversion.docling_converter import DoclingDocumentConverter
        source = tmp_path / "input.md"
        source.write_text("# Installed slim\n\nBody", encoding="utf-8")
        extraction = await DoclingDocumentConverter().extract(source, request.document_options)
        result = await document_artifacts.export_document_artifacts(extraction, request, tmp_path / "out")
    else:
        result = await markdown_rebuild.rebuild_document_artifacts("# Installed slim\n\nBody", json.dumps(original_review()),
                                                                  request, tmp_path / "out")
    assert result.review.processing.engine_version == "2.141.0"


def test_cpu_url_binding_requires_the_resolved_version_and_hash():
    from tools.lock_dependencies import bind_cpu_wheels

    wheels = {"torch": {"version": "2.15.0+cpu", "sha256": "a" * 64,
                        "url": "https://download-r2.pytorch.org/whl/cpu/fixture.whl"}}
    raw = "torch==2.15.0+cpu \\\n    --hash=sha256:" + "a" * 64 + "\n"
    bound = bind_cpu_wheels(raw, wheels)
    assert "torch @ https://download-r2.pytorch.org/" in bound
    with pytest.raises(ValueError):
        bind_cpu_wheels(raw.replace("a" * 64, "b" * 64), wheels)
    with pytest.raises(ValueError):
        bind_cpu_wheels(raw.replace("2.15.0", "2.14.0"), wheels)


def test_asset_verification_rejects_corruption_and_missing_files(tmp_path):
    from tools.verify_assets import verify_document

    asset = tmp_path / "model.bin"
    asset.write_bytes(b"fixture")
    lock = {"files": [{"path": "model.bin", "bytes": 7, "sha256": hashlib.sha256(b"fixture").hexdigest()}]}
    verify_document(tmp_path, lock)
    asset.write_bytes(b"changed")
    with pytest.raises(ValueError, match="checksum"):
        verify_document(tmp_path, lock)
    asset.unlink()
    with pytest.raises(FileNotFoundError):
        verify_document(tmp_path, lock)


@pytest.mark.parametrize("path", ["../model.bin", "/model.bin", "C:/model.bin", "a\\model.bin"])
def test_asset_verification_rejects_nonportable_paths(tmp_path, path):
    from tools.verify_assets import verify_document

    with pytest.raises(ValueError, match="relative"):
        verify_document(tmp_path, {"files": [{"path": path}]})
