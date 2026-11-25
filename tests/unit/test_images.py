"""N13 build inputs are exact, verified and independent of ambient model caches."""

import hashlib
import json
import locale
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]


def test_stage_document_copies_only_locked_bytes(tmp_path):
    from tools.check_images import stage_document

    source = tmp_path / "source"
    source.mkdir()
    (source / "model.bin").write_bytes(b"fixture")
    (source / "unrelated-secret").write_bytes(b"excluded")
    lock = {"files": [{"path": "model.bin", "bytes": 7,
                       "sha256": hashlib.sha256(b"fixture").hexdigest()}]}
    destination = tmp_path / "staged"
    stage_document(source, destination, lock)
    assert [p.name for p in destination.iterdir()] == ["model.bin"]
    assert (destination / "model.bin").read_bytes() == b"fixture"


def test_corrupt_assets_never_become_build_inputs(tmp_path):
    from tools.check_images import stage_document

    (tmp_path / "model.bin").write_bytes(b"changed")
    lock = {"files": [{"path": "model.bin", "bytes": 7, "sha256": "0" * 64}]}
    destination = tmp_path / "staged"
    with pytest.raises(ValueError, match="checksum"):
        stage_document(tmp_path, destination, lock)
    assert not destination.exists()


def test_image_commands_do_not_forward_host_credentials(tmp_path, monkeypatch):
    from tools.check_images import docker_environment

    monkeypatch.setenv("AZURE_CLIENT_SECRET", "do-not-forward")
    monkeypatch.setenv("DOCKER_AUTH_CONFIG", "do-not-forward")
    monkeypatch.setenv("DOCKER_HOST", "tcp://unapproved.invalid:2375")
    environment = docker_environment(tmp_path)
    assert not {"AZURE_CLIENT_SECRET", "DOCKER_AUTH_CONFIG", "DOCKER_HOST", "DOCKER_CONTEXT"} & environment.keys()
    assert json.loads((Path(environment["DOCKER_CONFIG"]) / "config.json").read_text()) == {}


@pytest.mark.parametrize("target", ["media", "index"])
def test_foreign_smoke_phase_is_rejected_instead_of_silently_skipped(target):
    from tools.check_images import smoke_phases

    with pytest.raises(ValueError, match="document"):
        smoke_phases(target, "inference")


def test_container_utf8_logs_survive_a_windows_locale(tmp_path, monkeypatch):
    from tools.check_images import run_command

    monkeypatch.setattr(locale, "getencoding", lambda: "cp1252")
    log = tmp_path / "model.log"
    text = "Loading ▏ Español"
    output = run_command([sys.executable, "-c", f"import sys; sys.stdout.buffer.write({text.encode('utf-8')!r})"],
                         environment={}, cwd=tmp_path, log=log)
    assert output == text and log.read_text(encoding="utf-8") == text


@pytest.mark.parametrize("target,command", [("document-converter", "akay-convert-document"),
                                           ("media-transcriber", "akay-transcribe-media"),
                                           ("content-indexer", "akay-index-content")])
def test_named_images_have_independent_exec_entries(target, command):
    text = (ROOT / "Dockerfile.workers").read_text()
    stage = text.split(f" AS {target}\n", 1)[1].split("\nFROM ", 1)[0]
    assert f'ENTRYPOINT ["{command}"]' in stage
    assert "EXPOSE " not in text
    assert "USER 10001:10001" in text
    assert "--require-hashes" in text
    assert "@sha256:" in text
