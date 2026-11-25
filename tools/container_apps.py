"""Prepare three offline ARM templates; apply one explicitly authorized existing app."""

import argparse
import copy
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys


API = "2025-07-01"
CLI_VERSION = "2.81.0"
COMMANDS = {"document": "akay-convert-document", "media": "akay-transcribe-media", "index": "akay-index-content"}
REPOSITORY = r"ghcr\.io/[a-z0-9]+(?:[._-][a-z0-9]+)*(?:/[a-z0-9]+(?:[._-][a-z0-9]+)*)+"
UUID = r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}"
BASE_ENV = {"AZURE_STORAGE_ACCOUNT_URL", "SOURCE_CONTAINER_NAME", "WEBHOOK_CALLBACKS", "WEBHOOK_API_KEY"}
PUBLICATION_ENV = {"DESTINATION_CONTAINER_NAME", "PUBLICATION_STATE_CONTAINER_NAME", "PUBLICATION_STATE_PREFIX"}
INDEX_ENV = {"INDEX_STATE_CONTAINER", "INDEX_STATE_PREFIX", "INDEX_PROFILES", "INDEX_QDRANT_URL", "INDEX_QDRANT_AUTH_MODE",
             "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_DEPLOYMENT", "AZURE_OPENAI_AUTH_MODE", "AZURE_OPENAI_API_KEY"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def matches(pattern, value):
    return isinstance(value, str) and re.fullmatch(pattern, value) is not None


def keys(value, expected):
    require(isinstance(value, dict) and set(value) == set(expected.split()), "Configuration has missing or unknown fields.")


def integer(value, minimum=1):
    require(type(value) is int and value >= minimum, "An explicit bounded integer setting is required.")


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "Duplicate configuration key.")
            result[key] = value
        return result

    def constant(_):
        raise ValueError("Non-finite JSON is forbidden.")

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)


def check_literals(value):
    # ARM interprets leading '[' as an expression. JSON-valued environment
    # strings are allowed, then escaped on serialization; expressions are not.
    if isinstance(value, str):
        require(bool(value.strip()) and value == value.strip(), "Blank or padded configuration value.")
        if value.startswith("["):
            strict_json(value)
    elif isinstance(value, dict):
        for key, item in value.items():
            check_literals(key)
            check_literals(item)
    elif isinstance(value, list):
        for item in value:
            check_literals(item)
    elif isinstance(value, float):
        require(math.isfinite(value), "Non-finite configuration value.")


def arm_literals(value):
    if isinstance(value, str):
        return "[" + value if value.startswith("[") else value
    if isinstance(value, dict):
        return {key: arm_literals(item) for key, item in value.items()}
    if isinstance(value, list):
        return [arm_literals(item) for item in value]
    return value


def validate_release(release, run, config, sha, run_id, attempt):
    require(matches(r"[0-9a-f]{40}", sha) and all(matches(r"[1-9][0-9]*", x) for x in (run_id, attempt)),
            "Exact commit/run/attempt identities are required.")
    identity = f"sha-{sha}-{run_id}-{attempt}"
    require(release.get("schemaVersion") == 1 and release.get("status") == "complete"
            and release.get("commit") == sha and release.get("releaseId") == identity
            and set(release.get("images", {})) == set(COMMANDS), "A complete matching N14 release is required.")
    require(run.get("id") == int(run_id) and run.get("run_attempt") == int(attempt) and run.get("head_sha") == sha
            and run.get("path") == ".github/workflows/build-and-push.yml" and run.get("head_branch") == "main"
            and run.get("event") == "workflow_dispatch" and run.get("conclusion") == "success",
            "Release metadata must identify a successful authorized main-branch publication workflow.")
    for target, image in release["images"].items():
        repository = config["workers"][target]["imageRepository"]
        require(matches(REPOSITORY, repository) and image.get("tag") == repository + ":" + identity
                and matches(re.escape(repository) + r"@sha256:[0-9a-f]{64}", image.get("digestRef"))
                and matches(r"sha256:[0-9a-f]{64}", image.get("imageId")), "Release image identity/repository mismatch.")
    return identity


def validate_worker(target, worker):
    keys(worker, "appName queueName imageRepository runtimeIdentity runtimeClientId scalerIdentity secretsIdentity "
                 "registryUsername registryPasswordSecret secrets resources workloadProfileName minReplicas maxReplicas "
                 "concurrency messageCount pollingInterval cooldownPeriod terminationGracePeriodSeconds env tags")
    require(matches(r"[a-z][a-z0-9-]{0,30}[a-z0-9]", worker["appName"]), "Invalid Container App name.")
    require(matches(r"[A-Za-z0-9][A-Za-z0-9._/-]*", worker["queueName"]), "Invalid queue name.")
    identity_pattern = (r"/subscriptions/" + UUID
                        + r"/resourceGroups/[^/]+/providers/Microsoft.ManagedIdentity/userAssignedIdentities/[^/]+")
    for field in ("runtimeIdentity", "scalerIdentity", "secretsIdentity"):
        require(matches(identity_pattern, worker[field]), "Explicit user-assigned identity resource IDs are required.")
    require(matches(UUID, worker["runtimeClientId"]), "Explicit runtime managed-identity client ID required.")
    require(matches(r"[A-Za-z0-9][A-Za-z0-9-]*", worker["registryUsername"])
            and matches(r"[A-Za-z0-9][A-Za-z0-9-]*", worker["workloadProfileName"]),
            "Explicit GHCR pull username and workload profile required.")
    for field in ("minReplicas", "cooldownPeriod"):
        integer(worker[field], 0)
    for field in ("maxReplicas", "concurrency", "messageCount", "pollingInterval", "terminationGracePeriodSeconds"):
        integer(worker[field])
    require(worker["minReplicas"] <= worker["maxReplicas"] <= 1000, "Invalid replica bounds.")
    require(target != "document" or worker["concurrency"] == 1, "Document concurrency starts at one per replica.")
    keys(worker["resources"], "cpu memory")
    cpu = worker["resources"]["cpu"]
    require(type(cpu) in (int, float) and math.isfinite(cpu) and cpu > 0
            and matches(r"[1-9][0-9]*(?:\.[0-9]+)?Gi|0\.[0-9]*[1-9][0-9]*Gi", worker["resources"]["memory"]),
            "Explicit positive CPU/memory required; Azure must validate workload-profile capacity.")
    require(isinstance(worker["tags"], dict) and all(isinstance(v, str) for v in worker["tags"].values()), "Invalid tags.")
    require(isinstance(worker["secrets"], list), "Key Vault secret references required.")
    names = set()
    for secret in worker["secrets"]:
        keys(secret, "name keyVaultUrl")
        require(matches(r"[a-z][a-z0-9-]{0,252}", secret["name"]) and secret["name"] not in names,
                "Secret names must be unique.")
        require(matches(r"https://[a-zA-Z0-9-]+\.vault\.azure\.net/secrets/[a-zA-Z0-9-]+/[a-zA-Z0-9]+", secret["keyVaultUrl"]),
                "Explicit versioned Azure Key Vault secret URI required, without credentials or query strings.")
        names.add(secret["name"])
    require(worker["registryPasswordSecret"] in names, "GHCR pull secret must be declared independently of OIDC/push.")
    env = worker["env"]
    required = BASE_ENV | (INDEX_ENV if target == "index" else PUBLICATION_ENV)
    if target == "media":
        required |= {"SPEECH_ENDPOINT", "SPEECH_RESOURCE_KEY"}
    require(isinstance(env, dict) and required <= set(env), "Missing required worker runtime configuration.")
    owned = {"AZURE_CLIENT_ID", "SERVICEBUS_FULLY_QUALIFIED_NAMESPACE", "SERVICEBUS_QUEUE_NAME", "TEMP_DIRECTORY", "TMPDIR",
             "MAX_CONCURRENT_JOBS", "DOCLING_ARTIFACTS_PATH", "INDEX_TOKENIZER_PATH"}
    owned |= {target.upper() + "_SERVICEBUS_QUEUE_NAME" for target in COMMANDS}
    require(not set(env) & owned and "SERVICEBUS_CONNECTION_STRING" not in env and "AZURE_STORAGE_SAS_TOKEN" not in env,
            "Routing/identity/assets/temp are generated; this deployment path uses managed identity for Blob/Service Bus.")
    for name, value in env.items():
        require(matches(r"[A-Z][A-Z0-9_]*", name), "Environment names must be uppercase.")
        if isinstance(value, dict):
            keys(value, "secretRef")
            require(value["secretRef"] in names, "Environment secret reference is missing.")
        else:
            require(isinstance(value, str) and not re.search(r"(?:^|_)(?:KEY|TOKEN|PASSWORD|CONNECTION_STRING)$", name),
                    "Secret environment values must use declared Key Vault references.")
    if target == "index":
        require(env["AZURE_OPENAI_AUTH_MODE"] == "apiKey", "Current index CLI requires explicit API-key mode.")
        require(env["INDEX_QDRANT_AUTH_MODE"] in {"apiKey", "none"}, "Invalid Qdrant authentication mode.")
        require(env["INDEX_QDRANT_AUTH_MODE"] != "apiKey" or "INDEX_QDRANT_API_KEY" in env, "Qdrant key reference missing.")
        require(isinstance(env["INDEX_PROFILES"], str) and bool(strict_json(env["INDEX_PROFILES"])),
                "Supply nonempty immutable index profile snapshots; startup performs their full runtime validation.")
    return names


def prepare(config, release, run, *, sha, run_id, attempt):
    keys(config, "schemaVersion subscriptionId resourceGroup environmentId location serviceBusNamespace legacyQueue workers")
    check_literals(config)
    require(type(config["schemaVersion"]) is int and config["schemaVersion"] == 1
            and matches(UUID, config["subscriptionId"]), "Invalid deployment schema/subscription.")
    require(matches(r"[A-Za-z0-9_.()-]+", config["resourceGroup"]), "Explicit resource group required.")
    require(matches(r"[a-zA-Z][a-zA-Z0-9-]*", config["serviceBusNamespace"]), "Explicit Service Bus namespace required.")
    require(matches(r"/subscriptions/" + UUID + r"/resourceGroups/[^/]+/providers/Microsoft.App/managedEnvironments/[^/]+",
                    config["environmentId"]), "Explicit standard Container Apps environment resource ID required.")
    require(set(config["workers"]) == set(COMMANDS), "Configure exactly three workers.")
    for target, worker in config["workers"].items():
        validate_worker(target, worker)
    for field in ("appName", "runtimeIdentity", "runtimeClientId", "imageRepository", "queueName"):
        values = [w[field].casefold() for w in config["workers"].values()]
        require(len(set(values)) == 3, "Workers need distinct apps, runtime identities, images and queues.")
        if field == "queueName":
            require(config["legacyQueue"].casefold() not in values, "Never consume a mixed legacy queue.")
    identity_sets = [{w[field].casefold() for field in ("runtimeIdentity", "scalerIdentity", "secretsIdentity")}
                     for w in config["workers"].values()]
    require(sum(map(len, identity_sets)) == len(set.union(*identity_sets)), "Do not share app identities across workers.")
    identity = validate_release(release, run, config, sha, run_id, attempt)
    plan = {"schemaVersion": 1, "releaseId": identity, "commit": sha,
            "subscriptionId": config["subscriptionId"], "resourceGroup": config["resourceGroup"], "workers": {}}
    for target, worker in config["workers"].items():
        env = copy.deepcopy(worker["env"])
        env.update(AZURE_CLIENT_ID=worker["runtimeClientId"],
                   SERVICEBUS_FULLY_QUALIFIED_NAMESPACE=config["serviceBusNamespace"] + ".servicebus.windows.net",
                   SERVICEBUS_QUEUE_NAME=config["legacyQueue"], TEMP_DIRECTORY="/tmp/akay", TMPDIR="/tmp",
                   MAX_CONCURRENT_JOBS=str(worker["concurrency"]))
        env.update({role.upper() + "_SERVICEBUS_QUEUE_NAME": spec["queueName"] for role, spec in config["workers"].items()})
        if target == "document":
            env["DOCLING_ARTIFACTS_PATH"] = "/opt/docling/models"
        if target == "index":
            env["INDEX_TOKENIZER_PATH"] = "/opt/tokenizers/cl100k_base.tiktoken"
        identities = {worker[field]: {} for field in ("runtimeIdentity", "scalerIdentity", "secretsIdentity")}
        resource = {
            "type": "Microsoft.App/containerApps", "apiVersion": API, "name": worker["appName"], "location": config["location"],
            "tags": dict(worker["tags"], **{"content-processing-release": identity}),
            "identity": {"type": "UserAssigned", "userAssignedIdentities": identities},
            "properties": {
                "environmentId": config["environmentId"], "workloadProfileName": worker["workloadProfileName"],
                "configuration": {
                    "activeRevisionsMode": "Single", "ingress": None,
                    "secrets": [dict(secret, identity=worker["secretsIdentity"]) for secret in worker["secrets"]],
                    "registries": [{"server": "ghcr.io", "username": worker["registryUsername"],
                                    "passwordSecretRef": worker["registryPasswordSecret"]}]},
                "template": {
                    "containers": [{"name": target, "image": release["images"][target]["digestRef"],
                                    "command": [COMMANDS[target]], "resources": worker["resources"],
                                    "env": [{"name": name, **(value if isinstance(value, dict) else {"value": value})}
                                            for name, value in sorted(env.items())],
                                    "volumeMounts": [{"volumeName": "scratch", "mountPath": "/tmp"}]}],
                    "volumes": [{"name": "scratch", "storageType": "EmptyDir"}],
                    "terminationGracePeriodSeconds": worker["terminationGracePeriodSeconds"],
                    "scale": {"minReplicas": worker["minReplicas"], "maxReplicas": worker["maxReplicas"],
                              "pollingInterval": worker["pollingInterval"], "cooldownPeriod": worker["cooldownPeriod"],
                              "rules": [{"name": "queue", "custom": {
                                  "type": "azure-servicebus", "identity": worker["scalerIdentity"],
                                  "metadata": {"queueName": worker["queueName"], "namespace": config["serviceBusNamespace"],
                                               "messageCount": str(worker["messageCount"])}}}]}}}}
        template = {"$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#",
                    "contentVersion": "1.0.0.0", "resources": [arm_literals(resource)]}
        app_id = (f"/subscriptions/{config['subscriptionId']}/resourceGroups/{config['resourceGroup']}"
                  f"/providers/Microsoft.App/containerApps/{worker['appName']}")
        plan["workers"][target] = {"appId": app_id, "template": template}
    return plan


def assert_subset(expected, actual):
    if isinstance(expected, dict):
        require(isinstance(actual, dict), "Control-plane configuration was not confirmed.")
        for key, value in expected.items():
            assert_subset(value, actual.get(key))
    elif isinstance(expected, list):
        require(isinstance(actual, list) and len(expected) == len(actual), "Control-plane inventory mismatch.")
        if expected and isinstance(expected[0], dict) and "name" in expected[0]:
            expected = sorted(expected, key=lambda item: item["name"])
            actual = sorted(actual, key=lambda item: item.get("name", ""))
        for wanted, observed in zip(expected, actual):
            assert_subset(wanted, observed)
    else:
        # Decode ARM's literal leading-bracket escape before comparing GET output.
        if isinstance(expected, str) and expected.startswith("[["):
            expected = expected[1:]
        require(expected == actual, "Control-plane value mismatch.")


def apply(plan, worker, directory, *, az):
    item = plan["workers"][worker]
    common = ["--subscription", plan["subscriptionId"], "--output", "json", "--only-show-errors"]
    show = ["resource", "show", "--ids", item["appId"], "--api-version", API, *common]
    existing = az(show)
    expected = item["template"]["resources"][0]
    require(existing.get("id", "").casefold() == item["appId"].casefold(), "Existing app identity mismatch.")
    props = existing["properties"]
    require((props.get("environmentId") or props.get("managedEnvironmentId")) == expected["properties"]["environmentId"]
            and existing["location"] == expected["location"], "Existing app environment/location mismatch; reconcile first.")
    require(len(props.get("template", {}).get("containers", [])) == 1
            and not props.get("template", {}).get("initContainers")
            and not props.get("configuration", {}).get("ingress"),
            "Reconcile existing ingress/sidecars before adopting the worker-only desired configuration.")
    command = ["deployment", "group", "--resource-group", plan["resourceGroup"],
               "--template-file", str(directory / f"{worker}.arm.json"), "--mode", "Incremental", *common]
    az([*command[:2], "validate", *command[2:]])
    result = az([*command[:2], "create", *command[2:]])
    require(result.get("properties", {}).get("provisioningState") == "Succeeded", "Deployment was not acknowledged.")
    actual = az(show)
    require(actual.get("properties", {}).get("provisioningState") == "Succeeded", "App provisioning is not confirmed.")
    assert_subset({key: value for key, value in expected.items() if key != "apiVersion"}, actual)
    return {"schemaVersion": 1, "status": "applied-control-plane-only", "worker": worker, "appId": item["appId"],
            "releaseId": plan["releaseId"], "commit": plan["commit"],
            "image": expected["properties"]["template"]["containers"][0]["image"]}


def write_json(path, value):
    with path.open("x", encoding="utf-8") as output:
        json.dump(value, output, indent=2, allow_nan=False)
        output.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="mode", required=True)
    build = commands.add_parser("prepare", help="Offline; no CLI, network, login or credential lookup")
    source = build.add_mutually_exclusive_group(required=True)
    source.add_argument("--config", type=Path)
    source.add_argument("--config-json")
    build.add_argument("--release", type=Path, required=True)
    build.add_argument("--run-metadata", type=Path, help="Omit to read explicit GitHub run metadata from stdin")
    for field in ("sha", "run-id", "attempt"):
        build.add_argument("--" + field, required=True)
    build.add_argument("--output", type=Path, required=True)
    deploy = commands.add_parser("apply", help="Requires explicit authorization and existing cloud resources")
    deploy.add_argument("--directory", type=Path, required=True)
    deploy.add_argument("--worker", choices=COMMANDS, required=True)
    deploy.add_argument("--apply", action="store_true")
    deploy.add_argument("--deployment-enabled", choices=["true", "false"], default="false")
    deploy.add_argument("--cutover-confirmed", action="store_true")
    deploy.add_argument("--azure-config", type=Path, help="Explicit dedicated OIDC login directory; no default user config")
    args = parser.parse_args()
    if args.mode == "prepare":
        config = strict_json(args.config.read_text(encoding="utf-8") if args.config else args.config_json)
        release = strict_json(args.release.read_text(encoding="utf-8"))
        run = strict_json(args.run_metadata.read_text(encoding="utf-8") if args.run_metadata else sys.stdin.read())
        plan = prepare(config, release, run, sha=args.sha, run_id=args.run_id, attempt=args.attempt)
        args.output.mkdir(parents=True, exist_ok=False)
        for worker, item in plan["workers"].items():
            write_json(args.output / f"{worker}.arm.json", item["template"])
        write_json(args.output / "deployment-plan.json", plan)
        print("PASS three offline templates prepared; no Azure or registry calls")
        return
    require(args.apply and args.deployment_enabled == "true" and args.cutover_confirmed,
            "Deployment is disabled without explicit apply, environment enablement and coordinated cutover.")
    require(args.azure_config is not None and args.azure_config.is_dir(), "Supply the dedicated authorized OIDC config directory.")
    plan = strict_json((args.directory / "deployment-plan.json").read_text(encoding="utf-8"))
    require(not (args.directory / f"{args.worker}.applied.json").exists(), "Do not overwrite earlier application evidence.")
    for worker, item in plan["workers"].items():
        require(strict_json((args.directory / f"{worker}.arm.json").read_text(encoding="utf-8")) == item["template"],
                "Prepared templates changed; prepare/review again.")

    def az(arguments):
        # Only the explicitly authorized workflow calls this boundary after OIDC.
        environment = {key: os.environ[key] for key in ("PATH", "SYSTEMROOT", "WINDIR") if key in os.environ}
        environment.update(AZURE_CONFIG_DIR=str(args.azure_config.resolve()), AZURE_CORE_COLLECT_TELEMETRY="false",
                           AZURE_EXTENSION_USE_DYNAMIC_INSTALL="no", AZURE_CORE_OUTPUT="none")
        result = subprocess.run(["az", *arguments], env=environment, check=True, capture_output=True, text=True, encoding="utf-8")
        return strict_json(result.stdout)

    require(az(["version", "--output", "json"]).get("azure-cli") == CLI_VERSION, "Use the pinned Azure CLI version.")
    result = apply(plan, args.worker, args.directory, az=az)
    write_json(args.directory / f"{args.worker}.applied.json", result)
    print("PASS selected app control-plane configuration acknowledged; service smoke remains pending")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError):
        # Never expose raw Azure errors, secret values or local configuration.
        print("Deployment preparation/application failed; inspect controlled inputs and cloud operation status.", file=sys.stderr)
        raise SystemExit(2)
