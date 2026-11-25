"""Validate the complete local smoke set; publish tested image IDs only on opt-in."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess


PHASES = {"document": {"startup", "rebuild", "models", "inference"},
          "media": {"startup"}, "index": {"startup"}}
IMAGE_ID = r"sha256:[0-9a-f]{64}"
REPOSITORY = r"ghcr\.io/[a-z0-9]+(?:[._-][a-z0-9]+)*(?:/[a-z0-9]+(?:[._-][a-z0-9]+)*)+"


def verify_evidence(data):
    if set(data) != set(PHASES):
        raise ValueError("All three image targets must be verified together.")
    for target, phases in PHASES.items():
        result = data[target]
        if not re.fullmatch(IMAGE_ID, result.get("imageId", "")):
            raise ValueError("Smoke evidence must identify an exact local image ID.")
        checks = result.get("checks", [])
        if {check["phase"] for check in checks} != phases or len(checks) != len(phases):
            raise ValueError("Every required smoke phase must pass.")
        for check in checks:
            state = check["state"]
            if state["ExitCode"] != 0 or state["OOMKilled"]:
                raise ValueError("A failed or OOM smoke cannot be released.")
            if not any(m.get("target") == target and m.get("phase") == check["phase"]
                       for m in check.get("measurements", [])):
                raise ValueError("Successful smoke measurements are required.")


def release_plan(data, repositories, sha, run_id, attempt):
    verify_evidence(data)
    if (set(repositories) != set(PHASES) or len(set(repositories.values())) != 3
            or any(not re.fullmatch(REPOSITORY, value) for value in repositories.values())):
        raise ValueError("Supply three distinct explicit lowercase GHCR repositories without tags.")
    if (not re.fullmatch(r"[0-9a-f]{40}", sha)
            or any(not re.fullmatch(r"[1-9][0-9]*", value) for value in (run_id, attempt))):
        raise ValueError("An exact commit SHA and positive workflow run/attempt identities are required.")
    release = f"sha-{sha}-{run_id}-{attempt}"
    return {"schemaVersion": 1, "commit": sha, "releaseId": release,
            "images": {name: {"imageId": data[name]["imageId"], "tag": repository + ":" + release}
                       for name, repository in repositories.items()}}


def publish(plan, directory, *, docker):
    directory.mkdir(parents=True, exist_ok=True)
    if (directory / "release.json").exists():
        raise FileExistsError("Refusing to republish an existing release attempt.")
    journal = directory / "publication.json"
    record = dict(plan, status="incomplete", images={name: dict(image) for name, image in plan["images"].items()})
    # A rerun must use its new run_attempt, not overwrite an earlier candidate.
    with journal.open("x", encoding="utf-8") as output:
        json.dump(record, output, indent=2)
    # Verify the complete set still exists before the first mutation. Always use
    # tested content-addressed IDs, never a mutable local tag or a fresh rebuild.
    for image in record["images"].values():
        info = json.loads(docker(["image", "inspect", image["imageId"]]))[0]
        if info["Id"] != image["imageId"]:
            raise ValueError("The tested image is no longer available.")
    for image in record["images"].values():
        docker(["image", "tag", image["imageId"], image["tag"]])
        docker(["image", "push", image["tag"]])
        repository = image["tag"].split(":")[0]
        info = json.loads(docker(["image", "inspect", image["tag"]]))[0]
        refs = [ref for ref in info.get("RepoDigests", [])
                if re.fullmatch(re.escape(repository) + "@" + IMAGE_ID, ref)]
        if len(refs) != 1:
            raise ValueError("A confirmed repository digest is required for each image.")
        image["digestRef"] = refs[0]
        journal.write_text(json.dumps(record, indent=2), encoding="utf-8")
    record["status"] = "complete"
    # No Git tag/release, semantic version allocation or mutable latest alias.
    with (directory / "release.json").open("x", encoding="utf-8") as output:
        json.dump(record, output, indent=2)
    print(f"PASS published complete image set {plan['releaseId']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    evidence = parser.add_mutually_exclusive_group(required=True)
    evidence.add_argument("--evidence-root", type=Path)
    evidence.add_argument("--results", type=Path, help="An explicit completed N13 result file for local reuse")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--attempt", required=True)
    parser.add_argument("--repositories-json")
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--docker-config", type=Path)
    parser.add_argument("--docker-host")
    args = parser.parse_args()
    results = [args.results] if args.results is not None else list(args.evidence_root.glob("run-*/results.json"))
    if len(results) != 1:
        parser.error("Supply a fresh evidence root with exactly one complete image check run.")
    data = json.loads(results[0].read_text(encoding="utf-8"))
    verify_evidence(data)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "build-verification.json").write_text(json.dumps({"commit": args.sha, "images": data}, indent=2), encoding="utf-8")
    if not args.publish:
        print("PASS all three tested images; publication disabled (no registry access)")
        return
    if (not args.repositories_json or args.docker_config is None or not args.docker_config.is_dir()
            or not args.docker_host or not args.docker_host.startswith(("unix://", "npipe://"))):
        parser.error("Publication requires explicit repositories, a dedicated login config and local Docker host.")
    plan = release_plan(data, json.loads(args.repositories_json), args.sha, args.run_id, args.attempt)
    environment = {key: os.environ[key] for key in ("PATH", "SYSTEMROOT", "TEMP", "TMP") if key in os.environ}
    environment["DOCKER_CONFIG"] = str(args.docker_config.resolve())

    def docker(arguments):
        return subprocess.run(["docker", "--host", args.docker_host, *arguments], env=environment,
                              check=True, capture_output=True, text=True, encoding="utf-8").stdout

    publish(plan, args.output, docker=docker)


if __name__ == "__main__":
    main()
