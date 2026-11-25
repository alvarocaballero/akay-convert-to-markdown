"""N14 release safety uses local evidence and fake Docker, never a registry."""

import hashlib
import importlib
import io
import json
from pathlib import Path
import sys

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
SHA = "a" * 40
REPOSITORIES = {name: f"ghcr.io/fixture/{name}" for name in ("document", "media", "index")}


def evidence():
    return {name: {"imageId": "sha256:" + str(i) * 64,
                   "checks": [{"phase": phase, "state": {"ExitCode": 0, "OOMKilled": False},
                               "measurements": [{"target": name, "phase": phase}]} for phase in phases]}
            for i, (name, phases) in enumerate((("document", ["startup", "rebuild", "models", "inference"]),
                                                ("media", ["startup"]), ("index", ["startup"])), 1)}


def test_workflow_tests_builds_and_smokes_before_explicit_publication():
    workflow = yaml.load((ROOT / ".github/workflows/build-and-push.yml").read_text(), Loader=yaml.BaseLoader)
    assert "pull_request" in workflow["on"]
    assert workflow["on"]["workflow_dispatch"]["inputs"]["publish"]["default"] == "false"
    assert workflow["permissions"] == {"contents": "read"}
    jobs = workflow["jobs"]
    assert jobs["images"]["needs"] == "test"
    steps = jobs["images"]["steps"]
    smoke = next(i for i, s in enumerate(steps) if "tools/check_images.py" in s.get("run", ""))
    login = next(i for i, s in enumerate(steps) if s.get("uses", "").startswith("docker/login-action@"))
    publish = next(i for i, s in enumerate(steps) if "--publish" in s.get("run", ""))
    assert smoke < login < publish
    for index in (login, publish):
        condition = steps[index]["if"]
        assert all(term in condition for term in ("workflow_dispatch", "inputs.publish", "vars.GHCR_PUBLICATION_ENABLED", "refs/heads/main"))
    assert "GHCR_IMAGE_REPOSITORIES" in steps[publish]["env"]
    text = (ROOT / ".github/workflows/build-and-push.yml").read_text()
    assert "git tag" not in text and "git push" not in text and ":latest" not in text
    assert "persist-credentials: false" in text
    assert "cancel-in-progress: false" in text
    assert "include-hidden-files: true" in text
    assert "docker-config" not in next(s["with"]["path"] for s in steps if s.get("uses", "").startswith("actions/upload-artifact@"))


def test_release_plan_has_one_nonreused_sha_identity_and_exact_tested_images():
    module = importlib.import_module("tools.ci_release")
    plan = module.release_plan(evidence(), REPOSITORIES, SHA, "123", "2")
    assert plan["releaseId"] == f"sha-{SHA}-123-2"
    assert set(plan["images"]) == set(REPOSITORIES)
    assert all(image["tag"].endswith(":" + plan["releaseId"]) for image in plan["images"].values())
    assert plan != module.release_plan(evidence(), REPOSITORIES, SHA, "123", "3")


@pytest.mark.parametrize("problem", ["missing-target", "missing-phase", "failed", "oom", "no-measurement", "bad-id"])
def test_incomplete_or_failed_smoke_never_becomes_a_release(problem):
    module = importlib.import_module("tools.ci_release")
    data = evidence()
    if problem == "missing-target":
        del data["index"]
    elif problem == "missing-phase":
        data["document"]["checks"].pop()
    elif problem == "bad-id":
        data["document"]["imageId"] = "untrusted:tag"
    else:
        check = data["document"]["checks"][0]
        if problem == "no-measurement":
            check["measurements"] = []
        else:
            check["state"]["OOMKilled" if problem == "oom" else "ExitCode"] = True if problem == "oom" else 1
    with pytest.raises(ValueError):
        module.release_plan(data, REPOSITORIES, SHA, "123", "1")


@pytest.mark.parametrize("repositories,sha,run,attempt", [({}, SHA, "123", "1"),
    (dict(REPOSITORIES, media=REPOSITORIES["index"]), SHA, "123", "1"),
    (dict(REPOSITORIES, media="ghcr.io/Owner/image:latest"), SHA, "123", "1"),
    (REPOSITORIES, "main", "123", "1"), (REPOSITORIES, SHA, "1;evil", "1")])
def test_release_rejects_invented_or_ambiguous_destinations(repositories, sha, run, attempt):
    module = importlib.import_module("tools.ci_release")
    with pytest.raises(ValueError):
        module.release_plan(evidence(), repositories, sha, run, attempt)


@pytest.mark.parametrize("fail_at", [None, "media"])
def test_publish_records_success_only_after_all_three_acknowledged_digests(tmp_path, fail_at):
    module = importlib.import_module("tools.ci_release")
    plan = module.release_plan(evidence(), REPOSITORIES, SHA, "123", "1")
    calls = []

    def docker(arguments):
        calls.append(arguments)
        if arguments[:2] == ["image", "push"]:
            if fail_at and f"/{fail_at}:" in arguments[-1]:
                raise RuntimeError("fixture transport failure")
            return ""
        if arguments[:2] == ["image", "inspect"]:
            identity = arguments[-1]
            if identity.startswith("sha256:"):
                return json.dumps([{"Id": identity}])
            return json.dumps([{"RepoDigests": [identity.split(":sha-")[0] + "@sha256:" + "f" * 64]}])
        return ""

    if fail_at:
        with pytest.raises(RuntimeError):
            module.publish(plan, tmp_path, docker=docker)
        assert not (tmp_path / "release.json").exists()
        assert json.loads((tmp_path / "publication.json").read_text())["status"] == "incomplete"
    else:
        module.publish(plan, tmp_path, docker=docker)
        release = json.loads((tmp_path / "release.json").read_text())
        assert release["status"] == "complete"
        assert len(release["images"]) == 3
        assert all("@sha256:" in image["digestRef"] for image in release["images"].values())
    assert all(call[:2] != ["buildx", "build"] for call in calls)
    assert len([c for c in calls if c[:2] == ["image", "inspect"] and c[-1].startswith("sha256:")]) == 3


def test_publication_does_not_reuse_an_existing_attempt(tmp_path):
    module = importlib.import_module("tools.ci_release")
    plan = module.release_plan(evidence(), REPOSITORIES, SHA, "123", "1")
    (tmp_path / "publication.json").write_text("{}")
    with pytest.raises(FileExistsError):
        module.publish(plan, tmp_path, docker=lambda args: pytest.fail("Must fail before Docker"))


def test_existing_success_record_prevents_any_publication(tmp_path):
    module = importlib.import_module("tools.ci_release")
    plan = module.release_plan(evidence(), REPOSITORIES, SHA, "123", "1")
    (tmp_path / "release.json").write_text("{}")
    with pytest.raises(FileExistsError):
        module.publish(plan, tmp_path, docker=lambda args: pytest.fail("Must fail before Docker"))


def test_dry_run_needs_no_destinations_credentials_or_docker(tmp_path, monkeypatch):
    module = importlib.import_module("tools.ci_release")
    run = tmp_path / "run-fixture"
    run.mkdir()
    (run / "results.json").write_text(json.dumps(evidence()))
    monkeypatch.setattr(sys, "argv", ["ci_release.py", "--evidence-root", str(tmp_path),
                                      "--output", str(tmp_path / "out"), "--sha", SHA,
                                      "--run-id", "123", "--attempt", "1"])
    monkeypatch.setattr(module.subprocess, "run", lambda *a, **k: pytest.fail("No Docker/registry in dry-run"))
    module.main()
    assert (tmp_path / "out/build-verification.json").is_file()
    assert not (tmp_path / "out/release.json").exists()


@pytest.mark.parametrize("response", ["missing-image", "missing-digest"])
def test_unconfirmed_publication_has_no_success_record(tmp_path, response):
    module = importlib.import_module("tools.ci_release")
    plan = module.release_plan(evidence(), REPOSITORIES, SHA, "123", "1")
    calls = []

    def docker(arguments):
        calls.append(arguments)
        if arguments[:2] == ["image", "inspect"]:
            if arguments[-1].startswith("sha256:"):
                return json.dumps([{"Id": "wrong" if response == "missing-image" else arguments[-1]}])
            return json.dumps([{"RepoDigests": []}])
        return ""

    with pytest.raises(ValueError):
        module.publish(plan, tmp_path, docker=docker)
    assert not (tmp_path / "release.json").exists()
    if response == "missing-image":
        assert not any(call[:2] == ["image", "push"] for call in calls)


def test_asset_fetch_is_opt_in_atomic_verified_and_reuses_existing_files(tmp_path):
    module = importlib.import_module("tools.ci_assets")
    target = tmp_path / "model.bin"
    data = b"fixture"
    expected = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    calls = []

    def open_url(url):
        calls.append(url)
        return io.BytesIO(data)

    with pytest.raises(FileNotFoundError):
        module.ensure_asset(target, expected, "https://fixture.invalid/model", download=False, open_url=open_url)
    assert calls == []
    module.ensure_asset(target, expected, "https://fixture.invalid/model", download=True, open_url=open_url)
    module.ensure_asset(target, expected, "https://fixture.invalid/model", download=False, open_url=open_url)
    assert target.read_bytes() == data and len(calls) == 1
    target.write_bytes(b"corrupt")
    with pytest.raises(ValueError):
        module.ensure_asset(target, expected, "https://fixture.invalid/model", download=True, open_url=open_url)
    assert len(calls) == 1


def test_invalid_download_is_not_published_as_a_cached_asset(tmp_path):
    module = importlib.import_module("tools.ci_assets")
    target = tmp_path / "model.bin"
    with pytest.raises(ValueError):
        module.ensure_asset(target, {"bytes": 3, "sha256": "0" * 64}, "https://fixture.invalid/model",
                            download=True, open_url=lambda url: io.BytesIO(b"bad-or-too-big"))
    assert not target.exists() and list(tmp_path.iterdir()) == []


def test_asset_sources_cover_exact_existing_locks_without_credentials():
    module = importlib.import_module("tools.ci_assets")
    assets = module.asset_inputs(ROOT)
    assert len(assets) == 20
    assert all(source.startswith("https://") and "@" not in source for _, _, source in assets)
    assert any("/resolve/8f39ad3c0b4c58e9c2d2c84a38465abf757272d8/" in source for _, _, source in assets)
    assert all("/v3.10.0/" in source for path, _, source in assets if path.as_posix().startswith("document/RapidOcr/"))
