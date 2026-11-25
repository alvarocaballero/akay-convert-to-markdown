"""N15 control-plane preparation; no Azure, registry or ambient credentials."""

import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
SHA = "a" * 40
SUB = "11111111-1111-1111-1111-111111111111"
PREFIX = f"/subscriptions/{SUB}/resourceGroups/fixture-rg/providers/"


def inputs():
    """Synthetic destinations are fixtures, never deployment defaults."""
    config = {"schemaVersion": 1, "subscriptionId": SUB, "resourceGroup": "fixture-rg",
              "environmentId": PREFIX + "Microsoft.App/managedEnvironments/fixture-env",
              "location": "westeurope", "serviceBusNamespace": "fixture-bus",
              "legacyQueue": "fixture-mixed", "workers": {}}
    for target in ("document", "media", "index"):
        identity = PREFIX + "Microsoft.ManagedIdentity/userAssignedIdentities/fixture-" + target
        env = {"AZURE_STORAGE_ACCOUNT_URL": "https://fixture.blob.core.windows.net",
               "SOURCE_CONTAINER_NAME": "fixture-source",
               "WEBHOOK_CALLBACKS": '{"result":"https://callback.invalid/result"}',
               "WEBHOOK_API_KEY": {"secretRef": "webhook"}}
        if target != "index":
            env.update(DESTINATION_CONTAINER_NAME="fixture-output", PUBLICATION_STATE_CONTAINER_NAME="fixture-state",
                       PUBLICATION_STATE_PREFIX="fixture-publication")
        if target == "media":
            env.update(SPEECH_ENDPOINT="https://speech.invalid", SPEECH_RESOURCE_KEY={"secretRef": "speech"})
        if target == "index":
            env.update(INDEX_STATE_CONTAINER="fixture-state", INDEX_STATE_PREFIX="fixture-index",
                       INDEX_PROFILES=json.dumps([{"id": "fixture-profile", "provider": "AzureOpenAI",
                                                   "model": "text-embedding-3-small", "deployment": "fixture-embedding",
                                                   "dimensions": 1536, "tokenizer": "cl100k_base", "maxChunkTokens": 600,
                                                   "distance": "Cosine", "collection": "fixture-collection"}]),
                       INDEX_QDRANT_URL="https://qdrant.invalid", INDEX_QDRANT_AUTH_MODE="apiKey",
                       INDEX_QDRANT_API_KEY={"secretRef": "qdrant"}, AZURE_OPENAI_ENDPOINT="https://embedding.invalid",
                       AZURE_OPENAI_DEPLOYMENT="fixture-embedding", AZURE_OPENAI_AUTH_MODE="apiKey",
                       AZURE_OPENAI_API_KEY={"secretRef": "embedding"})
        names = {"webhook", "pull"} | ({"speech"} if target == "media" else set())
        if target == "index":
            names |= {"qdrant", "embedding"}
        config["workers"][target] = {
            "appName": "fixture-" + target, "queueName": "fixture-" + target,
            "imageRepository": "ghcr.io/fixture/" + target,
            "runtimeIdentity": identity, "runtimeClientId": {"document": "2", "media": "3", "index": "4"}[target] * 8
            + "-1111-1111-1111-111111111111",
            "scalerIdentity": identity + "-scale", "secretsIdentity": identity + "-secrets",
            "registryUsername": "fixture-reader", "registryPasswordSecret": "pull",
            "secrets": [{"name": name, "keyVaultUrl": f"https://fixture.vault.azure.net/secrets/{name}/" + "b" * 32}
                        for name in sorted(names)],
            "resources": {"cpu": 2, "memory": "4Gi"}, "workloadProfileName": "Consumption",
            "minReplicas": 0, "maxReplicas": 2, "concurrency": 1,
            "messageCount": 1, "pollingInterval": 30, "cooldownPeriod": 300,
            "terminationGracePeriodSeconds": 600, "env": env, "tags": {"purpose": "fixture"}}
    release_id = f"sha-{SHA}-123-1"
    release = {"schemaVersion": 1, "status": "complete", "commit": SHA, "releaseId": release_id,
               "images": {target: {"imageId": "sha256:" + "c" * 64,
                                    "tag": f"ghcr.io/fixture/{target}:{release_id}",
                                    "digestRef": f"ghcr.io/fixture/{target}@sha256:" + str(n) * 64}
                          for n, target in enumerate(config["workers"], 1)}}
    run = {"id": 123, "run_attempt": 1, "head_sha": SHA, "head_branch": "main",
           "path": ".github/workflows/build-and-push.yml", "event": "workflow_dispatch", "conclusion": "success"}
    return config, release, run


@pytest.fixture
def deployment():
    spec = importlib.util.spec_from_file_location("container_apps", ROOT / "tools/container_apps.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def prepare(deployment, data=None):
    config, release, run = data or inputs()
    return deployment.prepare(config, release, run, sha=SHA, run_id="123", attempt="1")


def test_three_templates_have_exact_images_routes_identity_and_no_ingress(deployment):
    plan = prepare(deployment)
    for target, item in plan["workers"].items():
        template = item["template"]
        assert len(template["resources"]) == 1
        resource = template["resources"][0]
        assert resource["type"] == "Microsoft.App/containerApps"
        assert resource["apiVersion"] == "2025-07-01"
        props = resource["properties"]
        assert props["configuration"]["ingress"] is None
        assert props["configuration"]["activeRevisionsMode"] == "Single"
        container, = props["template"]["containers"]
        assert container["image"] == inputs()[1]["images"][target]["digestRef"]
        assert container["command"] == ["akay-" + {"document": "convert-document", "media": "transcribe-media",
                                                  "index": "index-content"}[target]]
        env = {entry["name"]: entry for entry in container["env"]}
        assert env[target.upper() + "_SERVICEBUS_QUEUE_NAME"]["value"] == "fixture-" + target
        assert env["MAX_CONCURRENT_JOBS"]["value"] == "1"
        assert env["TEMP_DIRECTORY"]["value"] == "/tmp/akay"
        rule, = props["template"]["scale"]["rules"]
        assert rule["custom"]["type"] == "azure-servicebus"
        assert rule["custom"]["metadata"]["queueName"] == "fixture-" + target
        assert rule["custom"]["identity"].endswith(target + "-scale")
        assert "auth" not in rule["custom"]
        assert container["volumeMounts"] == [{"volumeName": "scratch", "mountPath": "/tmp"}]
        assert props["template"]["volumes"] == [{"name": "scratch", "storageType": "EmptyDir"}]
        assert all("value" not in secret for secret in props["configuration"]["secrets"])
        assert props["configuration"]["registries"][0]["passwordSecretRef"] == "pull"


@pytest.mark.parametrize("mutation", [
    lambda c, r, m: r.update(status="incomplete"),
    lambda c, r, m: r["images"].pop("index"),
    lambda c, r, m: r["images"]["document"].update(digestRef="ghcr.io/fixture/document:latest"),
    lambda c, r, m: r["images"]["media"].update(digestRef="ghcr.io/other/media@sha256:" + "d" * 64),
    lambda c, r, m: r["images"]["index"].update(tag="ghcr.io/fixture/index:other-release"),
    lambda c, r, m: m.update(conclusion="failure"),
    lambda c, r, m: m.update(head_sha="b" * 40),
    lambda c, r, m: m.update(run_attempt=2),
    lambda c, r, m: m.update(path=".github/workflows/other.yml"),
    lambda c, r, m: c["workers"]["media"].update(queueName="FIXTURE-DOCUMENT"),
    lambda c, r, m: c.update(legacyQueue="fixture-document"),
    lambda c, r, m: c["workers"]["media"].update(appName="fixture-document"),
    lambda c, r, m: c["workers"]["document"].update(concurrency=2),
    lambda c, r, m: c["workers"]["index"].update(maxReplicas=0),
    lambda c, r, m: c["workers"]["index"]["env"].update(AZURE_OPENAI_AUTH_MODE="entra"),
    lambda c, r, m: c["workers"]["media"]["env"].update(SPEECH_RESOURCE_KEY="plaintext-secret"),
    lambda c, r, m: c["workers"]["document"]["env"].update(DOCUMENT_SERVICEBUS_QUEUE_NAME="wrong"),
    lambda c, r, m: c["workers"]["media"]["env"].pop("SPEECH_ENDPOINT"),
    lambda c, r, m: c["workers"]["index"]["secrets"][0].update(value="plaintext-secret"),
    lambda c, r, m: c["workers"]["index"].update(registryPasswordSecret="missing"),
    lambda c, r, m: c["workers"]["document"].update(resources={"cpu": False, "memory": "4Gi"}),
    lambda c, r, m: c["workers"]["document"]["env"].update(LOG_LEVEL="[parameters('injected')]"),
])
def test_incomplete_conflicting_or_unsafe_inputs_fail_closed(deployment, mutation):
    data = inputs()
    mutation(*data)
    with pytest.raises(ValueError):
        prepare(deployment, data)


def live_resource(item):
    resource = copy.deepcopy(item["template"]["resources"][0])
    # ARM GET responses do not echo the template's API version annotation.
    resource.pop("apiVersion")
    for entry in resource["properties"]["template"]["containers"][0]["env"]:
        if entry.get("value", "").startswith("[["):
            entry["value"] = entry["value"][1:]
    resource["id"] = item["appId"]
    resource["properties"].update(provisioningState="Succeeded", latestRevisionName="fixture-revision",
                                  latestReadyRevisionName="fixture-revision")
    return resource


@pytest.mark.parametrize("target", ["document", "media", "index"])
def test_apply_is_one_worker_scoped_and_checks_control_plane_after_ack(deployment, target):
    plan = prepare(deployment)
    calls = []
    item = plan["workers"][target]

    def az(args):
        calls.append(args)
        if args[:2] == ["resource", "show"]:
            return live_resource(item)
        return {"properties": {"provisioningState": "Succeeded"}}

    result = deployment.apply(plan, target, Path("fixture-plan"), az=az)
    assert result["status"] == "applied-control-plane-only"
    assert [args[:3] for args in calls] == [["resource", "show", "--ids"], ["deployment", "group", "validate"],
                                          ["deployment", "group", "create"], ["resource", "show", "--ids"]]
    assert all("--subscription" in args for args in calls)
    create = calls[2]
    assert create[create.index("--mode") + 1] == "Incremental"
    assert f"{target}.arm.json" in create[create.index("--template-file") + 1]
    assert all(f"{other}.arm.json" not in str(calls) for other in plan["workers"] if other != target)


@pytest.mark.parametrize("stage", ["missing-app", "different-environment", "failed-deployment", "wrong-image", "ingress"])
def test_no_success_for_missing_resources_or_unconfirmed_configuration(deployment, stage):
    plan = prepare(deployment)
    calls = []
    item = plan["workers"]["document"]

    def az(args):
        calls.append(args)
        if args[:2] == ["resource", "show"]:
            if stage == "missing-app":
                raise RuntimeError("not found")
            resource = live_resource(item)
            if stage == "different-environment":
                resource["properties"]["environmentId"] = PREFIX + "Microsoft.App/managedEnvironments/other"
            if len(calls) > 1:
                if stage == "wrong-image":
                    resource["properties"]["template"]["containers"][0]["image"] = "old:latest"
                if stage == "ingress":
                    resource["properties"]["configuration"]["ingress"] = {"external": True}
            return resource
        return {"properties": {"provisioningState": "Failed" if stage == "failed-deployment" else "Succeeded"}}

    with pytest.raises((ValueError, RuntimeError)):
        deployment.apply(plan, "document", Path("fixture-plan"), az=az)
    if stage in {"missing-app", "different-environment"}:
        assert len(calls) == 1


def test_real_cli_prepares_offline_without_reading_ambient_credentials(deployment, tmp_path):
    config, release, run = inputs()
    for name, value in (("config", config), ("release", release), ("run", run)):
        (tmp_path / f"{name}.json").write_text(json.dumps(value), encoding="utf-8")
    command = [sys.executable, str(ROOT / "tools/container_apps.py"), "prepare", "--config", str(tmp_path / "config.json"),
               "--release", str(tmp_path / "release.json"), "--run-metadata", str(tmp_path / "run.json"),
               "--sha", SHA, "--run-id", "123", "--attempt", "1", "--output", str(tmp_path / "prepared")]
    result = subprocess.run(command, capture_output=True, text=True,
                            env={key: os.environ[key] for key in ("SYSTEMROOT", "WINDIR") if key in os.environ})
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "prepared/document.arm.json").is_file()
    assert (tmp_path / "prepared/media.arm.json").is_file()
    assert (tmp_path / "prepared/index.arm.json").is_file()
    assert not (tmp_path / "prepared/applied.json").exists()
    denied = subprocess.run([sys.executable, str(ROOT / "tools/container_apps.py"), "apply", "--directory",
                             str(tmp_path / "prepared"), "--worker", "document"], capture_output=True, text=True)
    assert denied.returncode != 0
    assert not (tmp_path / "prepared/document.applied.json").exists()


def test_templates_use_exact_baked_asset_paths_and_escape_json_env(deployment):
    plan = prepare(deployment)
    for target, setting, path in (("document", "DOCLING_ARTIFACTS_PATH", "/opt/docling/models"),
                                  ("index", "INDEX_TOKENIZER_PATH", "/opt/tokenizers/cl100k_base.tiktoken")):
        container = plan["workers"][target]["template"]["resources"][0]["properties"]["template"]["containers"][0]
        values = {item["name"]: item.get("value") for item in container["env"]}
        assert values[setting] == path
    index = plan["workers"]["index"]["template"]["resources"][0]
    assert next(item["value"] for item in index["properties"]["template"]["containers"][0]["env"]
                if item["name"] == "INDEX_PROFILES").startswith("[[")


def test_non_secret_token_limits_remain_configurable_as_plain_values(deployment):
    data = inputs()
    data[0]["workers"]["index"]["env"]["AZURE_OPENAI_MAX_BATCH_TOKENS"] = "65536"
    plan = prepare(deployment, data)
    env = plan["workers"]["index"]["template"]["resources"][0]["properties"]["template"]["containers"][0]["env"]
    assert {"name": "AZURE_OPENAI_MAX_BATCH_TOKENS", "value": "65536"} in env


def test_runtime_secrets_and_scaler_identities_do_not_cross_app_boundaries(deployment):
    data = inputs()
    data[0]["workers"]["media"]["scalerIdentity"] = data[0]["workers"]["document"]["scalerIdentity"]
    with pytest.raises(ValueError):
        prepare(deployment, data)


@pytest.mark.parametrize("foreign", ["sidecar", "ingress"])
def test_apply_refuses_unmanaged_sidecar_and_existing_public_ingress_before_mutation(deployment, foreign):
    plan = prepare(deployment)
    calls = []

    def az(args):
        calls.append(args)
        resource = live_resource(plan["workers"]["document"])
        if foreign == "sidecar":
            resource["properties"]["template"]["containers"].append({"name": "unrelated-sidecar"})
        else:
            resource["properties"]["configuration"]["ingress"] = {"external": True}
        return resource

    with pytest.raises(ValueError):
        deployment.apply(plan, "document", Path("fixture-plan"), az=az)
    assert len(calls) == 1


def test_generated_environment_matches_existing_pinned_worker_settings(deployment, monkeypatch):
    from akay_convert_to_markdown.config.settings import DocumentWorkerSettings, MediaWorkerSettings, IndexerSettings
    from akay_convert_to_markdown.config.indexing_settings import IndexRuntimeSettings, AzureOpenAISettings

    plan = prepare(deployment)
    for target, settings in (("document", DocumentWorkerSettings), ("media", MediaWorkerSettings), ("index", IndexerSettings)):
        entries = plan["workers"][target]["template"]["resources"][0]["properties"]["template"]["containers"][0]["env"]
        env = {item["name"]: item.get("value", "synthetic-secret") for item in entries}
        env = {key: value[1:] if value.startswith("[[") else value for key, value in env.items()}
        with monkeypatch.context() as scoped:
            scoped.setattr(os, "environ", env)
            actual = settings()
            assert actual.servicebus_queue_name == "fixture-" + target
            assert actual.azure_client_id == inputs()[0]["workers"][target]["runtimeClientId"]
            if target == "index":
                assert IndexRuntimeSettings().profiles[0].deployment == AzureOpenAISettings().deployment


def test_explicit_apply_cli_scrubs_credentials_and_records_only_selected_ack(deployment, monkeypatch, tmp_path):
    plan = prepare(deployment)
    for target, item in plan["workers"].items():
        (tmp_path / f"{target}.arm.json").write_text(json.dumps(item["template"]), encoding="utf-8")
    (tmp_path / "deployment-plan.json").write_text(json.dumps(plan), encoding="utf-8")
    login = tmp_path / "authorized-login"
    login.mkdir()
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        assert kwargs["env"]["AZURE_CONFIG_DIR"] == str(login.resolve())
        assert not {"AZURE_CLIENT_SECRET", "AZURE_STORAGE_SAS_TOKEN", "GH_TOKEN", "HTTP_PROXY"} & set(kwargs["env"])
        if command[1] == "version":
            assert command[2:] == ["--output", "json"]
            result = {"azure-cli": "2.81.0"}
        elif command[1:3] == ["resource", "show"]:
            result = live_resource(plan["workers"]["media"])
        else:
            result = {"properties": {"provisioningState": "Succeeded"}}
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps(result))

    monkeypatch.setattr(deployment.subprocess, "run", run)
    for variable in ("AZURE_CLIENT_SECRET", "AZURE_STORAGE_SAS_TOKEN", "GH_TOKEN", "HTTP_PROXY"):
        monkeypatch.setenv(variable, "unrelated-ambient-secret")
    argv = ["container_apps.py", "apply", "--directory", str(tmp_path), "--worker", "media", "--apply",
            "--deployment-enabled", "true", "--cutover-confirmed", "--azure-config", str(login)]
    monkeypatch.setattr(sys, "argv", argv)
    deployment.main()
    assert len(calls) == 5
    assert json.loads((tmp_path / "media.applied.json").read_text())["status"] == "applied-control-plane-only"
    assert not (tmp_path / "document.applied.json").exists()
    # Reusing successful evidence cannot trigger another version probe or mutation.
    with pytest.raises(ValueError):
        deployment.main()
    assert len(calls) == 5


def test_apply_cli_rejects_changed_template_before_any_credential_or_cli_access(deployment, monkeypatch, tmp_path):
    plan = prepare(deployment)
    for target, item in plan["workers"].items():
        (tmp_path / f"{target}.arm.json").write_text(json.dumps(item["template"]), encoding="utf-8")
    (tmp_path / "deployment-plan.json").write_text(json.dumps(plan), encoding="utf-8")
    (tmp_path / "document.arm.json").write_text('{"resources": []}', encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["container_apps.py", "apply", "--directory", str(tmp_path), "--worker", "document",
                                     "--apply", "--deployment-enabled", "true", "--cutover-confirmed",
                                     "--azure-config", str(tmp_path)])
    monkeypatch.setattr(deployment.subprocess, "run", lambda *args, **kwargs: pytest.fail("No CLI access allowed"))
    with pytest.raises(ValueError):
        deployment.main()


def test_manual_deploy_workflow_has_separate_authority_and_pinned_control_plane():
    workflow = (ROOT / ".github/workflows/deploy-workers.yml").read_text(encoding="utf-8")
    assert "workflow_dispatch:" in workflow
    assert "  push:" not in workflow and "workflow_run:" not in workflow
    assert "inputs.authorize" in workflow and "inputs.cutover_confirmed" in workflow
    assert "environment: ${{ inputs.environment }}" in workflow
    assert "id-token: write" in workflow and "packages: write" not in workflow
    assert "DEPLOYMENT_ENABLED" in workflow and "== 'true'" in workflow
    assert workflow.index("container_apps.py prepare") < workflow.index("azure/login@v2")
    assert "actions/download-artifact@v4" in workflow and "run-id:" in workflow
    assert "azcliversion: '2.81.0'" in workflow
    assert "cancel-in-progress: false" in workflow
    assert "--worker" in workflow and "--apply" in workflow
