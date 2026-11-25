"""Audit/stage explicitly supplied existing caches for N3; never download models.

This is a local verification helper, not N12 packaging or runtime cache discovery.
Private registry APIs below are deliberately restricted to the exact tested pins.
"""

import argparse
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import re
import shutil
import sys


PINS = {"docling": "2.141.0", "docling-core": "2.99.0", "rapidocr": "3.10.0"}
LANGUAGES = ("es", "eu", "gl", "ca", "fr", "en", "de")


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def registry_hashes(value):
    if isinstance(value, dict):
        if "model_dir" in value and "SHA256" in value:
            yield value["model_dir"], value["SHA256"]
        for child in value.values():
            yield from registry_hashes(child)


def audit(hf_cache: Path, rapidocr_models: Path):
    actual = {package: version(package) for package in PINS}
    if actual != PINS:
        raise RuntimeError(f"Use the existing pinned environment: {PINS}; found {actual}")
    import rapidocr
    import yaml
    from docling.models.stages.ocr.rapid_ocr_model import (
        _backend_to_engine_type, _rapidocr_artifacts, _resolve_rapidocr,
    )

    files = {}
    snapshots = {}
    for repo, ref in (("docling-layout-heron", "main"), ("docling-models", "v2.3.0"),
                      ("CodeFormulaV2", "main")):
        cache = hf_cache / f"models--docling-project--{repo}"
        revision = (cache / "refs" / ref).read_text(encoding="utf-8").strip()
        if not re.fullmatch(r"[0-9a-f]{40}", revision):
            raise ValueError("Invalid local snapshot reference")
        source = cache / "snapshots" / revision
        snapshots[repo] = {"ref": ref, "snapshot": revision}
        if repo == "docling-models":
            selected = [source / "model_artifacts/tableformer/accurate" / name
                        for name in ("tm_config.json", "tableformer_accurate.safetensors")]
        else:
            # Processor/tokenizer configuration stays with its weights. No VLM description assets.
            selected = [*source.glob("*.json"), source / "model.safetensors"]
            if not (source / "config.json").is_file():
                raise FileNotFoundError(source / "config.json")
        for path in selected:
            files[f"docling-project--{repo}/{path.relative_to(source).as_posix()}"] = (path, None)

    registry = yaml.safe_load((Path(rapidocr.__file__).parent / "default_models.yaml").read_text(encoding="utf-8"))
    checksums = dict(registry_hashes(registry))
    languages = {}
    for language in LANGUAGES:
        spec = _resolve_rapidocr(f"iso:{language}", "onnxruntime")
        if spec.rapidocr_code != language:
            raise RuntimeError(f"Unexpected recognizer substitution: {language} -> {spec.rapidocr_code}")
        artifacts = _rapidocr_artifacts(rapidocr_models, _backend_to_engine_type("onnxruntime"),
                                       spec.ppocr_version, spec.rapidocr_code)
        resources = []
        for artifact in artifacts.values():
            for path, url in artifact.files.items():
                relative = f"RapidOcr/{path.name}"
                checksum = checksums.get(url)
                if checksum is None:
                    raise ValueError(f"Registry checksum unavailable for {url}")
                files[relative] = (path, checksum)
                resources.append(relative)
        languages[language] = {"recognizer": spec.rapidocr_code,
                               "backbone": spec.ppocr_version.value, "resources": resources,
                               "qualityVerified": False}

    inventory = []
    for relative, (source, expected) in sorted(files.items()):
        print(f"Auditing {relative} ({source.stat().st_size} bytes)", file=sys.stderr, flush=True)
        checksum = digest(source)
        if expected and checksum != expected.lower():
            raise ValueError(f"Registry checksum mismatch: {source}")
        # On installations with HF symlinks, LFS blob names also encode SHA256.
        blob = source.resolve().name
        if re.fullmatch(r"[0-9a-f]{64}", blob) and checksum != blob:
            raise ValueError(f"Cached HF blob checksum mismatch: {source}")
        inventory.append({"path": relative, "source": str(source), "bytes": source.stat().st_size,
                          "sha256": checksum, "registryChecksumVerified": expected is not None})
    return {"pins": actual, "snapshots": snapshots, "languages": languages, "files": inventory}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hf-cache", type=Path, required=True)
    parser.add_argument("--rapidocr-models", type=Path, required=True)
    parser.add_argument("--stage", type=Path, help="Copy only audited files into this explicit offline bundle")
    args = parser.parse_args()
    report = audit(args.hf_cache, args.rapidocr_models)
    if args.stage:
        for entry in report["files"]:
            target = args.stage / entry["path"]
            if target.exists():
                if digest(target) != entry["sha256"]:
                    raise FileExistsError(f"Refusing to overwrite a different local file: {target}")
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(entry["source"], target)
            if digest(target) != entry["sha256"]:
                raise ValueError(f"Staged copy checksum mismatch: {target}")
        (args.stage / "local-verification-audit.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
