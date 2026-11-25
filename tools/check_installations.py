"""Build one wheel and check three clean, locked installations on the host platform."""

import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tokenizer-file", type=Path, required=True)
    parser.add_argument("--target", choices=["document", "media", "index"], action="append")
    parser.add_argument("--label", default="initial", help="Fresh installation evidence directory label")
    parser.add_argument("--resume", action="store_true", help="Resume this tool's interrupted, initially clean venvs")
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9-]+", args.label):
        parser.error("Use an alphanumeric/hyphen label.")
    uv = shutil.which("uv")
    if uv is None:
        raise SystemExit("Install uv 0.11.16 first.")
    platform = "windows" if sys.platform == "win32" else "linux"
    environment = {key: os.environ[key] for key in ("PATH", "SYSTEMROOT", "TEMP", "TMP") if key in os.environ}
    home = ROOT / ".local/n12/tool-home"
    home.mkdir(parents=True, exist_ok=True)
    environment.update(HOME=str(home), USERPROFILE=str(home), APPDATA=str(home), XDG_CONFIG_HOME=str(home),
                       UV_CACHE_DIR=str(ROOT / ".local/n12/uv-cache"), UV_PYTHON_DOWNLOADS="never", UV_NO_PROGRESS="1",
                       UV_CONCURRENT_DOWNLOADS="1", UV_CONCURRENT_INSTALLS="1", UV_LINK_MODE="copy",
                       PIP_CONFIG_FILE=os.devnull, PIP_DISABLE_PIP_VERSION_CHECK="1")

    def run(arguments):
        subprocess.run([uv, *arguments, "--no-config"], cwd=ROOT, env=environment, check=True)

    run(["build", "--wheel", "--out-dir", ".local/n12/dist", "--default-index", "https://pypi.org/simple"])
    wheel = ROOT / ".local/n12/dist/akay_convert_to_markdown-1.0.1-py3-none-any.whl"
    for target in args.target or ["document", "media", "index"]:
        destination = ROOT / ".local/n12" / f"{target}-{args.label}"
        if destination.exists() and not args.resume:
            raise SystemExit(f"Refusing to reuse an existing installation: {destination}")
        if not destination.exists():
            run(["venv", str(destination), "--python", sys.executable, "--no-project", "--seed",
                 "--default-index", "https://pypi.org/simple"])
        python = destination / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        def pip(*arguments):
            subprocess.run([str(python), "-m", "pip", *arguments], cwd=ROOT, env=environment, check=True)

        pip("install", "--require-hashes", "--no-cache-dir", "--keyring-provider", "disabled",
            "--index-url", "https://pypi.org/simple",
            "-r", f"requirements/{target}-{platform}.txt")
        pip("install", "--no-deps", "--force-reinstall", str(wheel))
        pip("check")
        subprocess.run([str(python), "-I", str(ROOT / "tools/target_probe.py"), target,
                        "--tokenizer-file", str(args.tokenizer_file.resolve())],
                       cwd=ROOT, env=environment, check=True)


if __name__ == "__main__":
    main()
