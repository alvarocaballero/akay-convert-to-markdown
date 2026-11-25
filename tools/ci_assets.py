"""Prepare only the public assets in the existing locks; downloads require opt-in."""

import argparse
import json
from pathlib import Path
import tempfile
from urllib.request import HTTPSHandler, HTTPRedirectHandler, ProxyHandler, build_opener

try:
    from tools.verify_assets import verify_file
except ModuleNotFoundError:
    from verify_assets import verify_file


ROOT = Path(__file__).resolve().parents[1]
RAPID_BASE = "https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.10.0/onnx/"
RAPID_PATHS = {"PP-OCRv6_det_small.onnx": "PP-OCRv6/det/PP-OCRv6_det_small.onnx",
               "PP-OCRv6_rec_small.onnx": "PP-OCRv6/rec/PP-OCRv6_rec_small.onnx",
               "ch_ppocr_mobile_v2.0_cls_mobile.onnx": "PP-OCRv4/cls/ch_ppocr_mobile_v2.0_cls_mobile.onnx"}


class HTTPSRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        if not newurl.startswith("https://"):
            raise ValueError("Public asset redirects must retain HTTPS.")
        return super().redirect_request(request, fp, code, message, headers, newurl)


def asset_inputs(root):
    lock = json.loads((root / "requirements/document-models.json").read_text())
    assets = []
    for entry in lock["files"]:
        prefix, relative = entry["path"].split("/", 1)
        if prefix == "RapidOcr":
            source = RAPID_BASE + RAPID_PATHS[relative]
        else:
            snapshot = lock["snapshots"][prefix]
            source = f"https://huggingface.co/{snapshot['repository']}/resolve/{snapshot['revision']}/{relative}"
        assets.append((Path("document") / entry["path"], entry, source))
    tokenizer = json.loads((root / "requirements/index-tokenizer.json").read_text())
    assets.append((Path("tokenizer/cl100k_base.tiktoken"), tokenizer, tokenizer["url"]))
    return assets


def ensure_asset(path, expected, source, *, download=False, open_url):
    if path.exists():
        verify_file(path, expected)
        return
    if not download:
        raise FileNotFoundError(f"Missing locked asset: {path.name}; download opt-in is required.")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as output:
            temporary = Path(output.name)
            # Tokenizer lock has no length; keep a conservative bounded transfer.
            limit, count = expected.get("bytes", 4 * 1024 * 1024), 0
            with open_url(source) as response:
                while chunk := response.read(1024 * 1024):
                    count += len(chunk)
                    if count > limit:
                        raise ValueError("Public asset exceeds its locked size limit.")
                    output.write(chunk)
        verify_file(temporary, expected)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--download-public-assets", action="store_true")
    parser.add_argument("--list-sources", action="store_true")
    args = parser.parse_args()
    # No proxy discovery, netrc, HF token, CLI login or user model cache.
    opener = build_opener(ProxyHandler({}), HTTPSHandler(), HTTPSRedirects())
    for relative, expected, source in asset_inputs(ROOT):
        if args.list_sources:
            print(f"{relative.as_posix()} <- {source} sha256={expected['sha256']}")
            continue
        ensure_asset(args.directory / relative, expected, source, download=args.download_public_assets,
                     open_url=lambda url: opener.open(url, timeout=120))
    if not args.list_sources:
        print("PASS 20 locked public assets; existing bytes reused and all hashes verified")


if __name__ == "__main__":
    main()
