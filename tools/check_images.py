"""Build/check N13 images locally, with explicit assets and an empty Docker config."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

try:
    from tools.verify_assets import verify_document, verify_file
except ModuleNotFoundError:
    from verify_assets import verify_document, verify_file


ROOT = Path(__file__).resolve().parents[1]
TARGETS = {"document": ("document-converter", "akay-convert-document"),
           "media": ("media-transcriber", "akay-transcribe-media"),
           "index": ("content-indexer", "akay-index-content")}


def smoke_phases(target, selection):
    phases = ["startup", "rebuild", "models", "inference"] if target == "document" else ["startup"]
    if selection == "all":
        return phases
    if target == "document" and selection == "layout-diagnostic":
        return [selection]
    if selection not in phases:
        raise ValueError("This smoke phase requires the document target.")
    return [selection]


def stage_document(source, destination, lock):
    verify_document(source, lock)
    destination.mkdir(parents=True, exist_ok=False)
    for entry in lock["files"]:
        output = destination / entry["path"]
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / entry["path"], output)
    verify_document(destination, lock)


def docker_environment(directory):
    directory.mkdir(parents=True, exist_ok=True)
    config = directory / "docker-config"
    config.mkdir(exist_ok=True)
    # Tool-owned fresh config, never a copy of the user's registry credentials.
    (config / "config.json").write_text("{}\n", encoding="utf-8")
    environment = {key: os.environ[key] for key in ("PATH", "SYSTEMROOT", "TEMP", "TMP") if key in os.environ}
    environment.update(DOCKER_CONFIG=str(config), HOME=str(directory), USERPROFILE=str(directory),
                       APPDATA=str(directory), BUILDX_NO_DEFAULT_ATTESTATIONS="1")
    return environment


def run_command(command, *, environment, cwd, capture=False, log=None):
    result = subprocess.run(command, cwd=cwd, env=environment, text=True, encoding="utf-8",
                            stdout=subprocess.PIPE if capture or log else None,
                            stderr=subprocess.STDOUT if log else None)
    if log:
        log.write_text(result.stdout, encoding="utf-8")
        print(result.stdout, end="", flush=True)
    result.check_returncode()
    return result.stdout


def main():
    # Docker/model logs are UTF-8, including progress glyphs; Windows' default
    # redirected console encoding may otherwise fail after a successful check.
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--document-models", type=Path, required=True)
    parser.add_argument("--tokenizer-file", type=Path, required=True)
    parser.add_argument("--target", choices=TARGETS, action="append")
    parser.add_argument("--docker-host", required=True, help="Explicit local Docker engine URI; no ambient context")
    parser.add_argument("--buildx-plugin", type=Path, help="Explicit buildx binary when installed only in the user's CLI directory")
    parser.add_argument("--skip-build", action="store_true", help="Repeat smoke checks on already built local N13 tags")
    parser.add_argument("--smoke", choices=["startup", "rebuild", "models", "inference", "layout-diagnostic", "all"], default="all")
    args = parser.parse_args()
    if not args.docker_host.startswith(("npipe://", "unix://")):
        parser.error("Only an explicit local Docker engine is supported.")
    targets = args.target or list(TARGETS)
    for target in targets:
        try:
            smoke_phases(target, args.smoke)
        except ValueError as error:
            parser.error(str(error))
    evidence = ROOT / ".local/n13"
    evidence.mkdir(parents=True, exist_ok=True)
    run_dir = Path(tempfile.mkdtemp(prefix="run-", dir=evidence))
    environment = docker_environment(run_dir)
    if args.buildx_plugin is not None:
        plugins = Path(environment["DOCKER_CONFIG"]) / "cli-plugins"
        plugins.mkdir()
        shutil.copyfile(args.buildx_plugin, plugins / args.buildx_plugin.name)
        (plugins / args.buildx_plugin.name).chmod(0o755)
    docker = ["docker", "--host", args.docker_host]

    def run(arguments, *, capture=False, log=None):
        command = [*docker, *arguments]
        with (run_dir / "commands.jsonl").open("a", encoding="utf-8") as record:
            record.write(json.dumps(command) + "\n")
        return run_command(command, environment=environment, cwd=ROOT, capture=capture, log=log)

    print(f"Evidence directory: {run_dir}", flush=True)
    document_lock = json.loads((ROOT / "requirements/document-models.json").read_text())
    tokenizer_lock = json.loads((ROOT / "requirements/index-tokenizer.json").read_text())
    if "document" in targets and not args.skip_build:
        stage_document(args.document_models.resolve(), run_dir / "document", document_lock)
    if "index" in targets and not args.skip_build:
        verify_file(args.tokenizer_file, tokenizer_lock)
        (run_dir / "tokenizer").mkdir()
        shutil.copyfile(args.tokenizer_file, run_dir / "tokenizer/cl100k_base.tiktoken")
    checks = run_dir / "checks"
    checks.mkdir()
    for name in ("target_probe.py", "container_smoke.py", "verify_assets.py"):
        shutil.copyfile(ROOT / "tools" / name, checks / name)
    shutil.copyfile(ROOT / "tests/docling_fixtures.py", checks / "docling_fixtures.py")
    # No repository/host home bind mount or forwarded environment/credential.
    results = {}
    for target in targets:
        stage, command = TARGETS[target]
        tag = f"akay-n13-{target}:local"
        if not args.skip_build:
            contexts = (["--build-context", f"document_assets={run_dir / 'document'}"] if target == "document" else
                        ["--build-context", f"tokenizer_assets={run_dir / 'tokenizer'}"] if target == "index" else [])
            run(["buildx", "build", "--load", "--platform", "linux/amd64", "--progress", "plain",
                 "--file", "Dockerfile.workers", "--target", stage, "--tag", tag, *contexts, "."])
        info = json.loads(run(["image", "inspect", tag], capture=True))[0]
        assert info["Config"]["User"] == "10001:10001"
        assert info["Config"]["Entrypoint"] == [command]
        assert not info["Config"].get("ExposedPorts")
        observations = {"imageId": info["Id"], "sizeBytes": info["Size"], "checks": []}
        results[target] = observations
        phases = smoke_phases(target, args.smoke)
        for phase in phases:
            name = f"akay-n13-{target}-{phase}-{run_dir.name}"
            start = time.monotonic()
            succeeded = False
            try:
                output = run(["run", "--name", name, "--network", "none", "--read-only", "--cap-drop", "ALL",
                     "--security-opt", "no-new-privileges", "--cpus", "2", "--memory", "4g", "--pids-limit", "256",
                     "--tmpfs", "/tmp/akay:rw,nosuid,nodev,size=1073741824,uid=10001,gid=10001,mode=700",
                     "--mount", f"type=bind,source={checks},target=/checks,readonly", "--entrypoint", "python", tag,
                     "-I", "/checks/container_smoke.py", target, phase], log=run_dir / f"{target}-{phase}.log")
                measurements = [json.loads(line) for line in output.splitlines()
                                if line.startswith('{"target":') and '"phase":' in line]
                succeeded = True
            finally:
                stats = run(["inspect", name, "--format", "{{json .State}}"], capture=True)
                observations["checks"].append({"phase": phase, "elapsedSeconds": round(time.monotonic() - start, 2),
                                               "state": json.loads(stats), "measurements": measurements if succeeded else []})
                (run_dir / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
                # Remove only this tool's exact stopped container; never prune user resources.
                run(["rm", "--force", name])
        print(json.dumps({target: observations}), flush=True)


if __name__ == "__main__":
    main()
