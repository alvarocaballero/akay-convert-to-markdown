"""Offline checks executed inside the actual N13 runtime images, never production jobs."""

import argparse
import asyncio
import importlib.abc
import json
import os
from pathlib import Path
import resource
import runpy
import socket
import subprocess
import sys
import tempfile
import time


CHECKS = Path(__file__).resolve().parent


def forbidden(*args, **kwargs):
    raise AssertionError("Container smoke checks cannot fetch assets or contact services.")


def offline():
    socket.socket.connect = socket.socket.connect_ex = socket.create_connection = socket.getaddrinfo = forbidden
    os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")


async def rebuild():
    class NoExtraction(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            if fullname.startswith(("docling.pipeline.", "docling.models.stages.")):
                raise AssertionError("Reconstruction must not initialize extraction models/pipelines.")

    sys.meta_path.insert(0, NoExtraction())
    from akay_convert_to_markdown.contracts.artifacts import Review, ReviewSummary, Processing
    from akay_convert_to_markdown.contracts.requests import DocumentRequest
    from akay_convert_to_markdown.conversion.markdown_rebuild import rebuild_document_artifacts

    request = DocumentRequest.model_validate_json(json.dumps({
        "schemaVersion": 1, "requestId": "b1ad362f-0911-4773-8651-1508d94ca005", "contentKey": "fixture",
        "operation": "rebuildFromMarkdown", "source": {"type": "blob", "blobName": "draft.md"},
        "contentType": "document", "callback": "fixture", "documentOptions": {"extractSections": True}}))
    review = Review(schema_version=1, content_key="fixture", content_type="document",
                    source={"type": "blob", "blobName": "original.pdf"}, summary=ReviewSummary(),
                    processing=Processing(operation="convert", engine="docling", engine_version="2.141.0"))
    with tempfile.TemporaryDirectory() as directory:
        result = await rebuild_document_artifacts("# Corrected heading\n\nCorrected text.\n\n![edited](https://invalid.invalid/x)\n",
                                                  review.model_dump_json(by_alias=True), request, Path(directory) / "result")
        assert not list((Path(directory) / "result").glob("*.md"))
    assert "Corrected text" in result.markdown and result.review.sections
    assert result.review.confidence.pages == []
    assert not any(name.startswith(("docling.pipeline.", "docling.models.stages.")) for name in sys.modules)
    print("PASS fresh-process rebuild; no extraction models/pipelines, image fetching or download", flush=True)


async def inference(*, strict_layout=False):
    # Reuse the same generated N3 fixtures and integration assertions, without
    # installing pytest/test packages into the delivered runtime.
    from docling_fixtures import write_spanish_scan_pdf, write_structured_pdf
    from akay_convert_to_markdown.contracts.requests import DocumentOptions
    from akay_convert_to_markdown.conversion.docling_converter import DoclingDocumentConverter
    from docling_core.types.doc import DoclingDocument
    import re

    models = Path("/opt/docling/models")
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        for broken in (False, True):
            source = root / f"scan-{broken}.pdf"
            write_spanish_scan_pdf(source, broken_text_layer=broken)
            extracted = await DoclingDocumentConverter(artifacts_path=models).extract(source, DocumentOptions())
            assert "plantas" in extracted.document.export_to_markdown().casefold()
            await extracted.export_referenced(root / f"scan-{broken}")
            loaded = DoclingDocument.load_from_json(root / f"scan-{broken}/document.docling.json")
            assert [item.text for item in loaded.texts] == [item.text for item in extracted.document.texts]
            assert all(page.image is None for page in loaded.pages.values())
            assert extracted.confidence.pages
            print(f"PASS Spanish raster OCR integration brokenTextLayer={broken}; accent fidelity not certified", flush=True)
        source = root / "structured.pdf"
        write_structured_pdf(source)
        for code, formula in ((False, False), (True, False), (False, True), (True, True)):
            start = time.monotonic()
            extracted = await DoclingDocumentConverter(artifacts_path=models).extract(
                source, DocumentOptions(code_enrichment=code, formula_enrichment=formula))
            output = root / f"flags-{code}-{formula}"
            await extracted.export_referenced(output)
            loaded = DoclingDocument.load_from_json(output / "document.docling.json")
            markdown = extracted.document.export_to_markdown()
            assert "Fotosíntesis" in markdown and "energía luminosa" in markdown, repr(markdown)
            assert "Agua" in markdown and "Plantas" in markdown and "energia" in markdown
            assert loaded.tables and loaded.pictures
            assert any(item.label == "code" for item in loaded.texts)
            formula_detected = any(item.label == "formula" for item in loaded.texts)
            if strict_layout:
                assert formula_detected, "Native fixture formula was not classified as a formula on Linux."
            if code:
                assert any(item.label == "code" and "\n" in item.text for item in loaded.texts)
            if formula and formula_detected:
                assert any(item.label == "formula" and "E=mc^2" in re.sub(r"[\s{}]", "", item.text) for item in loaded.texts)
            elif formula_detected:
                assert "<!-- formula-not-decoded -->" in markdown
            assert all(page.image is None for page in loaded.pages.values())
            saved = json.loads((output / "document.docling.json").read_text())
            for item in saved["pictures"]:
                uri = item["image"]["uri"]
                assert uri.startswith("images/") and (output / uri).is_file()
                assert uri in (output / "document.md").read_text()
            print(json.dumps({"PASS": "PDF extraction with requested enrichment flags", "code": code,
                              "formula": formula, "formulaDetected": formula_detected,
                              "elapsedSeconds": round(time.monotonic() - start, 2)}), flush=True)
        if not strict_layout:
            await known_regions(source, models)


async def known_regions(source, models):
    """Test real enrichment independently of platform-dependent layout classification.

    Ground-truth regions belong only to this fixture; they never patch pipeline
    output or add a fallback to application conversion.
    """
    from akay_convert_to_markdown.contracts.requests import DocumentOptions
    from akay_convert_to_markdown.conversion.docling_converter import build_docling_converter
    from docling.datamodel.base_models import InputFormat, ItemAndImageEnrichmentElement
    from docling.models.stages.code_formula.code_formula_vlm_model import CodeFormulaVlmModel
    from docling_core.types.doc import DoclingDocument, DocItemLabel
    import pypdfium2

    engine = build_docling_converter(DocumentOptions(code_enrichment=True, formula_enrichment=True),
                                     artifacts_path=models, input_format=InputFormat.PDF)
    engine.initialize_pipeline(InputFormat.PDF)
    pipeline = next(iter(engine.initialized_pipelines.values()))
    stage = next(model for model in pipeline.enrichment_pipe if isinstance(model, CodeFormulaVlmModel))
    document = DoclingDocument(name="fixture-ground-truth-regions")
    code = document.add_code(text="unrecognized code")
    formula = document.add_text(label=DocItemLabel.FORMULA, text="unrecognized formula")
    pdf = pypdfium2.PdfDocument(source)
    page = pdf[0]
    bitmap = page.render(scale=1.67)
    image = bitmap.to_pil().copy()
    bitmap.close()
    page.close()
    pdf.close()
    regions = [(code, (45, 305, 420, 420)), (formula, (110, 470, 250, 525))]
    for item, box in regions:
        assert stage.is_processable(document, item)
        crop = image.crop(tuple(round(value * 1.67) for value in box))
        output = list(stage(document, [ItemAndImageEnrichmentElement(item=item, image=crop)]))
        assert len(output) == 1 and output[0].text.strip() and not output[0].text.startswith("unrecognized")
        print(json.dumps({"PASS": "real local CodeFormulaV2 ground-truth crop inference", "label": str(item.label),
                          "outputCharacters": len(output[0].text)}), flush=True)


async def media_tools():
    from deno import find_deno_bin
    from yt_dlp_ejs.yt import solver
    from akay_convert_to_markdown.config.settings import MediaSettings
    from akay_convert_to_markdown.services.ffmpeg_service import FfmpegService

    def run(*command):
        return subprocess.run(command, check=True, capture_output=True, text=True, env={"PATH": os.defpath, "HOME": "/tmp/akay"})

    print(run("/usr/bin/ffmpeg", "-version").stdout.splitlines()[0])
    print(run("/usr/bin/ffprobe", "-version").stdout.splitlines()[0])
    print(run(str(find_deno_bin()), "--version").stdout)
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "audio.webm"
        run("/usr/bin/ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=1", "-c:a", "libopus", str(source))
        service = FfmpegService(MediaSettings(servicebus_queue_name="probe-only", ffmpeg_timeout_seconds=30,
                                               ffmpeg_max_log_bytes=8192))
        info = await service.probe_media(source)
        assert info.audio_codec == "opus" and 0.9 < info.duration_seconds < 1.2
        output = await service.prepare_audio(source, root, media=info)
        assert output.suffix == ".ogg" and output.stat().st_size > 0
        script = root / "ejs.js"
        script.write_text(solver.lib() + "\nObject.assign(globalThis, lib);\n" + solver.core() + '\nconsole.log("EJS loaded");\n')
        assert "EJS loaded" in run(str(find_deno_bin()), "run", "--no-config", "--no-remote", "--no-prompt", str(script)).stdout
    print("PASS real FFmpeg/FFprobe audio-only WebM extraction and pinned offline Deno/EJS", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=["document", "media", "index"])
    parser.add_argument("phase", choices=["startup", "rebuild", "models", "inference", "layout-diagnostic"])
    args = parser.parse_args()
    assert os.getuid() == os.getgid() == 10001
    assert not os.access("/app", os.W_OK)
    assert os.access("/tmp/akay", os.W_OK)
    assert os.environ["TMPDIR"] == "/tmp/akay"
    sys.path.insert(0, str(CHECKS))  # Only explicit probe files, never application source.
    if args.target == "document":
        from verify_assets import verify_document
        lock = json.loads(Path("/app/requirements/document-models.json").read_text())
        models = Path("/opt/docling/models")
        verify_document(models, lock)
        assert {str(path.relative_to(models)) for path in models.rglob("*") if path.is_file()} == {
            entry["path"] for entry in lock["files"]}
        assert not os.access(models, os.W_OK) and not Path("/opt/tokenizers").exists()
    elif args.target == "index":
        from verify_assets import verify_file
        verify_file(Path("/opt/tokenizers/cl100k_base.tiktoken"),
                    json.loads(Path("/app/requirements/index-tokenizer.json").read_text()))
        assert not Path("/opt/docling").exists()
    else:
        assert not Path("/opt/docling").exists() and not Path("/opt/tokenizers").exists()
    start = time.monotonic()
    offline()
    if args.phase == "startup":
        sys.argv = [str(CHECKS / "target_probe.py"), args.target, "--scratch-dir", "/tmp/akay",
                    "--tokenizer-file", "/opt/tokenizers/cl100k_base.tiktoken"]
        runpy.run_path(str(CHECKS / "target_probe.py"), run_name="__main__")
        if args.target == "media":
            os.environ["PATH"] = os.defpath
            asyncio.run(media_tools())
    elif args.phase == "rebuild":
        asyncio.run(rebuild())
    elif args.phase == "models":
        from target_probe import local_models
        local_models(Path("/opt/docling/models"))
    else:
        asyncio.run(inference(strict_layout=args.phase == "layout-diagnostic"))
    usage = resource.getrusage(resource.RUSAGE_SELF)
    peak = Path("/sys/fs/cgroup/memory.peak")
    print(json.dumps({"target": args.target, "phase": args.phase, "elapsedSeconds": round(time.monotonic() - start, 2),
                      "maxRssKiB": usage.ru_maxrss, "cpuSeconds": round(usage.ru_utime + usage.ru_stime, 2),
                      "cgroupMemoryPeakBytes": int(peak.read_text()) if peak.exists() else None}), flush=True)


if __name__ == "__main__":
    main()
