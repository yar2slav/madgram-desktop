import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import zipfile


ROOT = Path(__file__).resolve().parents[1]


def git(directory, *args):
    return subprocess.check_output(["git", "-C", str(directory), *args], text=True, encoding="utf-8").strip()


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    upstream = (ROOT / "UPSTREAM").read_text(encoding="utf-8").strip()
    if not re.fullmatch(re.escape(upstream) + r"-mad\.[1-9][0-9]*", args.tag):
        raise SystemExit("release tag must match UPSTREAM and contain a positive mad release number")
    source = ROOT.parent / "tdesktop"
    build = source / "out/release-build/Release"
    output = args.output.resolve()
    standalone = output / "mad.exe"
    if not standalone.is_file():
        raise SystemExit("package mad.exe first")
    files = {
        "mad.exe": build / "mad.exe",
        "modules/x64/d3d/d3dcompiler_47.dll": build / "modules/x64/d3d/d3dcompiler_47.dll",
        "LICENSE": source / "LICENSE",
        "LEGAL": source / "LEGAL",
    }
    archive = output / f"mad-{args.tag}-win64.zip"
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as target:
        for name, path in files.items():
            target.write(path, name)
    with zipfile.ZipFile(archive) as target:
        if set(target.namelist()) != set(files) or target.testzip() is not None:
            raise SystemExit("invalid portable archive")
        for name, path in files.items():
            if hashlib.sha256(target.read(name)).hexdigest() != digest(path):
                raise SystemExit("portable archive content mismatch")
    manifest = {
        "tag": args.tag,
        "upstream": upstream,
        "queue_commit": git(ROOT, "rev-parse", "HEAD"),
        "source_tree": git(source, "rev-parse", "HEAD^{tree}"),
        "submodules": git(source, "submodule", "status", "--recursive").splitlines(),
        "patches": {path.relative_to(ROOT).as_posix(): digest(path) for path in sorted((ROOT / "patches").rglob("*.patch"))},
        "files": {name: digest(path) for name, path in files.items()},
        "automatic_updates": True,
    }
    manifest_file = output / "source-manifest.json"
    manifest_file.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    hashes = "".join(f"{digest(path)}  {path.name}\n" for path in (standalone, archive, manifest_file))
    (output / "SHA256SUMS").write_text(hashes, encoding="utf-8")
    notes = (ROOT / "ci/release-notes.md").read_text(encoding="utf-8")
    (output / "release-notes.md").write_text(
        notes.replace("{tag}", args.tag).replace("{upstream}", upstream),
        encoding="utf-8",
    )
    print(f"release files verified: {args.tag}")


if __name__ == "__main__":
    main()
