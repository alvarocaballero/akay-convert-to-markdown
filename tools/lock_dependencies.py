"""Resolve N12 CPU/Python 3.12 target locks against public package indexes only."""

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def bind_cpu_wheels(text, wheels):
    # uv 0.11.16 does not emit its torch-backend index into requirements output.
    # Bind only the resolved CPU entries to official, hash-matching wheel URLs so
    # pip installs the same artifacts without another index or backend heuristic.
    for name, wheel in wheels.items():
        pattern = rf"^{name}=={re.escape(wheel['version'])} \\\n(?:    --hash=sha256:[0-9a-f]+(?: \\)?\n)+"
        matches = list(re.finditer(pattern, text, re.MULTILINE))
        if len(matches) != 1 or f"--hash=sha256:{wheel['sha256']}" not in matches[0].group():
            raise ValueError(f"Resolved CPU wheel/version/hash disagrees with its lock: {name}")
        replacement = f"{name} @ {wheel['url']} \\\n    --hash=sha256:{wheel['sha256']}\n"
        text = text[:matches[0].start()] + replacement + text[matches[0].end():]
    return text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", choices=["windows", "linux"], action="append")
    parser.add_argument("--target", choices=["document", "media", "index"], action="append")
    parser.add_argument("--check", action="store_true", help="Fail if regenerating changes an existing lock")
    args = parser.parse_args()
    uv = shutil.which("uv")
    if uv is None:
        raise SystemExit("Install uv 0.11.16 before compiling locks.")
    if subprocess.check_output([uv, "--version"], text=True).split()[1] != "0.11.16":
        raise SystemExit("Use the verified uv 0.11.16 resolver.")
    environment = {key: os.environ[key] for key in ("PATH", "SYSTEMROOT", "TEMP", "TMP") if key in os.environ}
    # Empty tool home avoids .netrc/auth/config discovery. No application secrets
    # or package-index environment settings are passed to the resolver.
    home = ROOT / ".local/n12/tool-home"
    home.mkdir(parents=True, exist_ok=True)
    environment.update(HOME=str(home), USERPROFILE=str(home), APPDATA=str(home),
                       XDG_CONFIG_HOME=str(home), UV_CACHE_DIR=str(ROOT / ".local/n12/uv-cache"),
                       UV_PYTHON_DOWNLOADS="never", UV_NO_PROGRESS="1")
    for platform in args.platform or ["windows", "linux"]:
        triple = "x86_64-pc-windows-msvc" if platform == "windows" else "x86_64-manylinux_2_28"
        for target in args.target or ["document", "media", "index"]:
            path = ROOT / f"requirements/{target}-{platform}.txt"
            before = path.read_bytes() if args.check else None
            command = [uv, "pip", "compile", "pyproject.toml", "--extra", target,
                       "--constraint", "requirements/compatibility.txt", "--python-version", "3.12",
                       "--python-platform", triple, "--generate-hashes", "--no-annotate", "--no-header",
                       "--emit-index-url", "--torch-backend", "cpu", "--no-config",
                       "--keyring-provider", "disabled", "--default-index", "https://pypi.org/simple",
                       "--output-file", f"requirements/{target}-{platform}.txt", "--quiet"]
            subprocess.run(command, cwd=ROOT, env=environment, check=True)
            if target == "document":
                wheels = json.loads((ROOT / "requirements/cpu-wheels.json").read_text())[platform]
                path.write_text(bind_cpu_wheels(path.read_text(), wheels), encoding="utf-8", newline="\n")
            if before is not None and path.read_bytes() != before:
                raise SystemExit(f"Lock regeneration changed {path.name}; inspect the dependency update.")
            print(f"PASS resolved {target}-{platform}", flush=True)


if __name__ == "__main__":
    main()
