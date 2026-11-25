"""N16 handoff: real processing seams, explicit doubles and a loopback receiver."""

import importlib
import json
import os
from pathlib import Path
import socket
import threading

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]


def receiver_api():
    return importlib.import_module("tools.callback_receiver")


def sample_event():
    from akay_convert_to_markdown.contracts.events import conversion_completed
    from akay_convert_to_markdown.contracts.artifacts import ArtifactLayout
    from akay_convert_to_markdown.contracts.requests import parse_request

    examples = json.loads((ROOT / "tests/fixtures/content_processing/handoff-requests.json").read_text())
    job = parse_request(json.dumps(examples["principal"]), worker="document", callbacks={"local"})
    event = conversion_completed(job, ArtifactLayout.for_destination(job.destination_blob_name).document_refs())
    return event.model_dump(mode="json", by_alias=True)


def test_handoff_examples_are_complete_valid_routed_requests():
    from akay_convert_to_markdown.contracts.requests import parse_request

    examples = json.loads((ROOT / "tests/fixtures/content_processing/handoff-requests.json").read_text())
    routes = {"principal": "document", "additional": "document", "rebuild": "document",
              "audio": "media", "video": "media", "youtube": "media", "indexPrincipal": "index",
              "indexAdditional": "index", "indexTranscript": "index", "reassign": "index",
              "deletePrincipal": "index", "deleteTranscript": "index"}
    assert set(examples) == set(routes)
    jobs = {name: parse_request(json.dumps(raw), worker=routes[name], callbacks={"local"})
            for name, raw in examples.items()}
    assert len({job.request_id for job in jobs.values()}) == len(jobs)
    assert jobs["rebuild"].content_key == jobs["principal"].content_key
    assert jobs["indexPrincipal"].source.blob_name.startswith("principal/extracted.artifacts/")
    assert jobs["indexTranscript"].source.blob_name.startswith("media/corrected/")
    assert [jobs[k].operation_sequence for k in ("indexTranscript", "deleteTranscript", "reassign")] == [1, 2, 3]


def test_callback_inbox_auth_identity_deduplication_and_conflict():
    api = receiver_api()
    inbox = api.CallbackInbox("fixture-key")
    event = sample_event()
    key = f"{event['requestId']}:{event['eventType']}"
    raw = json.dumps(event).encode()
    assert inbox.accept(raw, "wrong", key) == 401
    assert inbox.accept(raw, "fixture-key", "wrong") == 400
    assert inbox.accept(b'{"schemaVersion": NaN}', "fixture-key", key) == 400
    assert not inbox.events
    assert inbox.accept(raw, "fixture-key", key) == 200
    assert inbox.accept(json.dumps(event, indent=2).encode(), "fixture-key", key) == 200
    changed = dict(event, payload={"changed": True})
    assert inbox.accept(json.dumps(changed).encode(), "fixture-key", key) == 409
    assert len(inbox.events) == 1


def test_callback_inbox_bounds_and_lost_acknowledgement():
    api = receiver_api()
    inbox = api.CallbackInbox("fixture-key", fail_after_accept=True, max_events=1)
    event = sample_event()
    key = f"{event['requestId']}:{event['eventType']}"
    assert inbox.accept(b"x" * (api.MAX_BODY_BYTES + 1), "fixture-key", key) == 413
    assert inbox.accept(json.dumps(event).encode(), "fixture-key", key) == 503
    assert inbox.accept(json.dumps(event).encode(), "fixture-key", key) == 200
    other = dict(event, requestId="b1ad362f-0911-4773-8651-1508d94cafff")
    assert inbox.accept(json.dumps(other).encode(), "fixture-key", f"{other['requestId']}:{other['eventType']}") == 503
    assert len(inbox.events) == 1


async def test_actual_loopback_receiver_with_real_webhook_retry():
    from tests.helpers import make_settings
    from akay_convert_to_markdown.notifications.webhook_client import WebhookClient

    api = receiver_api()
    inbox = api.CallbackInbox("fixture-key", fail_after_accept=True)
    server = api.create_server(inbox, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    assert server.server_address[0] == "127.0.0.1"
    url = f"http://127.0.0.1:{server.server_address[1]}/callbacks"
    try:
        async with httpx.AsyncClient(trust_env=False) as client:
            settings = make_settings(webhook_callbacks={"local": url}, webhook_api_key="fixture-key")
            webhook = WebhookClient(settings, client)
            event = sample_event()
            await webhook.send("local", event, f"{event['requestId']}:{event['eventType']}")
            assert len(inbox.events) == 1 and inbox.deliveries == 2
            assert (await client.post(url + "/unknown", content=b"{}")).status_code == 404
            assert (await client.post(url, content=b"{}", headers={"Content-Length": "2"})).status_code == 401
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    assert not thread.is_alive()


async def test_offline_end_to_end_handoff_preserves_final_inputs_and_detached_resources(tmp_path):
    from tests.unit.test_content_chunking import CharacterTokenizer

    demo = importlib.import_module("tools.content_processing_demo")
    report = await demo.run_demo(tmp_path / "evidence", tokenizer=CharacterTokenizer(limit=8192))
    assert report["status"] == "passed-local-only"
    assert report["settlements"]["abandoned"] == 2
    assert report["checks"] == ["reviewed-principal", "additional-document", "blob-audio-video-youtube-doubles",
                                "corrected-transcript", "callback-only-replay", "scoped-delete-and-stale-rejection",
                                "detach-and-reassign-without-reconversion", "persistent-local-qdrant"]
    assert report["semanticEmbeddings"] is False
    assert report["externalServices"] is False
    assert json.loads((tmp_path / "evidence/report.json").read_text()) == report
    assert (tmp_path / "evidence/artifacts/principal/extracted.artifacts/review.json").is_file()


async def test_demo_scrubs_environment_blocks_network_and_restores_state(tmp_path, monkeypatch):
    demo = importlib.import_module("tools.content_processing_demo")
    monkeypatch.setenv("AZURE_CLIENT_SECRET", "synthetic-sentinel-never-use")
    monkeypatch.setenv("HTTP_PROXY", "http://synthetic-proxy.invalid")
    original = socket.socket.connect

    async def guarded(directory, tokenizer):
        assert "AZURE_CLIENT_SECRET" not in os.environ and "HTTP_PROXY" not in os.environ
        assert Path(os.environ["HOME"]).parent == directory
        for operation in (lambda: socket.getaddrinfo("service.invalid", 443),
                          lambda: socket.create_connection(("service.invalid", 443))):
            with pytest.raises(AssertionError, match="cannot contact"):
                operation()
        raise RuntimeError("fixture interruption")

    monkeypatch.setattr(demo, "_run", guarded)
    with pytest.raises(RuntimeError, match="fixture interruption"):
        await demo.run_demo(tmp_path / "owned", tokenizer=None)
    assert socket.socket.connect is original
    assert os.environ["AZURE_CLIENT_SECRET"] == "synthetic-sentinel-never-use"
    with pytest.raises(FileExistsError):
        await demo.run_demo(tmp_path / "owned", tokenizer=None)
