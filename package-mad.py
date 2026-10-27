import argparse
import ctypes
import hashlib
import lzma
import os
from pathlib import Path
import runpy
import shutil
import struct
import subprocess
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parent
SDK_URL = "https://github.com/ip7z/7zip/releases/download/26.05/lzma2605.7z"
SDK_SHA256 = "668fda469b7f584f246008cf28359c66ef98d65fafb3b22a52672eebe6970c28"


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def set_icon(executable, icon):
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LoadLibraryExW.argtypes = [ctypes.c_wchar_p, ctypes.c_void_p, ctypes.c_uint]
    kernel.LoadLibraryExW.restype = ctypes.c_void_p
    kernel.FreeLibrary.argtypes = [ctypes.c_void_p]
    callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ssize_t)
    groups = []
    def collect(module, kind, name, parameter):
        groups.append(name if name < 65536 else ctypes.wstring_at(name))
        return True
    callback = callback_type(collect)
    kernel.EnumResourceNamesW.argtypes = [ctypes.c_void_p, ctypes.c_void_p, callback_type, ctypes.c_ssize_t]
    module = kernel.LoadLibraryExW(str(executable), None, 2)
    if not module:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        kernel.EnumResourceNamesW(module, 14, callback, 0)
        language_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ushort, ctypes.c_ssize_t)
        resources = []
        def collect_language(module, kind, name, language, parameter):
            resources.append((name if name < 65536 else ctypes.wstring_at(name), language))
            return True
        languages = language_type(collect_language)
        kernel.EnumResourceLanguagesW.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, language_type, ctypes.c_ssize_t]
        for name in groups:
            pointer = ctypes.c_void_p(name) if isinstance(name, int) else ctypes.cast(ctypes.c_wchar_p(name), ctypes.c_void_p)
            kernel.EnumResourceLanguagesW(module, 14, pointer, languages, 0)
    finally:
        kernel.FreeLibrary(module)
    kernel.BeginUpdateResourceW.argtypes = [ctypes.c_wchar_p, ctypes.c_bool]
    kernel.BeginUpdateResourceW.restype = ctypes.c_void_p
    kernel.UpdateResourceW.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ushort, ctypes.c_void_p, ctypes.c_uint]
    kernel.EndUpdateResourceW.argtypes = [ctypes.c_void_p, ctypes.c_bool]
    handle = kernel.BeginUpdateResourceW(str(executable), False)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        raw = icon.read_bytes()
        count = struct.unpack_from("<H", raw, 4)[0]
        group = bytearray(raw[:6])
        for index in range(count):
            width, height, colors, reserved, planes, bits, size, offset = struct.unpack_from("<BBBBHHII", raw, 6 + index * 16)
            entry = raw[offset:offset + size]
            resource_id = 7000 + index
            blob = ctypes.create_string_buffer(entry)
            if not kernel.UpdateResourceW(handle, 3, resource_id, 0, blob, len(entry)):
                raise ctypes.WinError(ctypes.get_last_error())
            group += struct.pack("<BBBBHHIH", width, height, colors, reserved, planes, bits, size, resource_id)
        blob = ctypes.create_string_buffer(bytes(group))
        for name, language in resources or [(1, 0)]:
            pointer = ctypes.c_void_p(name) if isinstance(name, int) else ctypes.cast(ctypes.c_wchar_p(name), ctypes.c_void_p)
            if not kernel.UpdateResourceW(handle, 14, pointer, language, blob, len(group)):
                raise ctypes.WinError(ctypes.get_last_error())
        if not kernel.EndUpdateResourceW(handle, False):
            raise ctypes.WinError(ctypes.get_last_error())
        handle = None
    finally:
        if handle:
            kernel.EndUpdateResourceW(handle, True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path.home() / "Downloads/mad.exe")
    parser.add_argument("--sdk", type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise SystemExit("output already exists; choose another filename")
    seven = Path(os.environ["ProgramFiles"]) / "7-Zip/7z.exe"
    build = ROOT.parent / "tdesktop/out/release-build/Release"
    files = {
        "mad.exe": build / "mad.exe",
        "modules/x64/d3d/d3dcompiler_47.dll": build / "modules/x64/d3d/d3dcompiler_47.dll",
        "LICENSE": ROOT.parent / "tdesktop/LICENSE",
        "LEGAL": ROOT.parent / "tdesktop/LEGAL",
    }
    hashes = {name: digest(path) for name, path in files.items()}
    build_id = hashlib.sha256("".join(hashes.values()).encode()).hexdigest()[:24]
    with tempfile.TemporaryDirectory(prefix="mad-single-build-") as temporary:
        temporary = Path(temporary)
        sdk = args.sdk or temporary / "sdk.7z"
        if not args.sdk:
            urllib.request.urlretrieve(SDK_URL, sdk)
        if digest(sdk) != SDK_SHA256:
            raise SystemExit("sdk checksum mismatch")
        subprocess.run([str(seven), "x", str(sdk), "C/LzmaDec.c", "C/LzmaDec.h", "C/7zTypes.h", "C/Precomp.h", "C/Compiler.h", f"-o{temporary}", "-y"], check=True, stdout=subprocess.DEVNULL)
        header = f'constexpr auto kBuild = L"{build_id}";\nstruct PackageFile {{ const wchar_t *path; const char *sha256; unsigned short resource; size_t size; }};\nconstexpr PackageFile kFiles[] = {{\n'
        resources = ["LANGUAGE 9, 1"]
        for index, (name, path) in enumerate(files.items()):
            resource_id = 100 + index
            payload = temporary / f"payload-{index}.lzma"
            payload.write_bytes(lzma.compress(path.read_bytes(), format=lzma.FORMAT_ALONE, preset=6))
            header += f'{{ L"{name}", "{hashes[name]}", {resource_id}, {path.stat().st_size} }},\n'
            resources.append(f'{resource_id} RCDATA "{payload.as_posix()}"')
        header += '};\n'
        (temporary / "package_files.h").write_text(header, encoding="utf-8")
        resource_source = temporary / "package.rc"
        resource_source.write_text("\n".join(resources) + "\n", encoding="utf-8")
        environment = runpy.run_path(str(ROOT / "prepare-mad-release.py"))["build_environment"]()
        compiler = shutil.which("cl.exe", path=environment["PATH"])
        resource_compiler = shutil.which("rc.exe", path=environment["PATH"])
        decoder = temporary / "decoder.obj"
        resource_object = temporary / "package.res"
        candidate = temporary / "mad.exe"
        subprocess.run([compiler, "/nologo", "/O2", "/MT", "/TC", "/c", str(temporary / "C/LzmaDec.c"), f"/Fo:{decoder}"], cwd=temporary, env=environment, check=True)
        subprocess.run([resource_compiler, "/nologo", "/c65001", f"/fo{resource_object}", str(resource_source)], cwd=temporary, env=environment, check=True)
        subprocess.run([compiler, "/nologo", "/std:c++17", "/O2", "/MT", "/EHsc", "/utf-8", "/DUNICODE", "/D_UNICODE", f"/I{temporary}", f"/I{temporary / 'C'}", str(ROOT / "packaging/single-launcher.cpp"), str(decoder), str(resource_object), f"/Fe:{candidate}", f"/Fo:{temporary / 'launcher.obj'}", "/link", "/SUBSYSTEM:WINDOWS", "/MANIFEST:EMBED", "/MANIFESTUAC:level='asInvoker' uiAccess='false'", "shell32.lib", "ole32.lib", "user32.lib", "bcrypt.lib", "uuid.lib"], cwd=temporary, env=environment, check=True)
        set_icon(candidate, ROOT.parent / "tdesktop/Telegram/Resources/art/icon256.ico")
        test_root = temporary / "test profile with spaces"
        command = [str(candidate), "--prepare-only", str(test_root)]
        subprocess.run(command, check=True)
        sentinel = test_root / "profile/keep.txt"
        sentinel.write_text("keep my profile", encoding="utf-8")
        app = test_root / "app" / build_id
        original_times = {name: (app / name).stat().st_mtime_ns for name in files}
        subprocess.run(command, check=True)
        assert all((app / name).stat().st_mtime_ns == original_times[name] for name in files)
        (app / "modules/x64/d3d/d3dcompiler_47.dll").write_bytes(b"damaged")
        subprocess.run(command, check=True)
        assert (app / "mad.exe").stat().st_mtime_ns == original_times["mad.exe"]
        assert sentinel.read_text() == "keep my profile"
        for name, hash_value in hashes.items():
            assert digest(app / name) == hash_value
        assert not list(test_root.rglob("*.tmp-*"))
        damaged = temporary / "damaged-payload.exe"
        shutil.copy2(candidate, damaged)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.BeginUpdateResourceW.argtypes = [ctypes.c_wchar_p, ctypes.c_bool]
        kernel.BeginUpdateResourceW.restype = ctypes.c_void_p
        kernel.UpdateResourceW.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ushort, ctypes.c_void_p, ctypes.c_uint]
        kernel.EndUpdateResourceW.argtypes = [ctypes.c_void_p, ctypes.c_bool]
        handle = kernel.BeginUpdateResourceW(str(damaged), False)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        if not kernel.UpdateResourceW(handle, 10, 100, 1033, None, 0):
            kernel.EndUpdateResourceW(handle, True)
            raise ctypes.WinError(ctypes.get_last_error())
        if not kernel.EndUpdateResourceW(handle, False):
            raise ctypes.WinError(ctypes.get_last_error())
        subprocess.run([str(damaged), "--prepare-only", str(test_root)], check=True)
        assert all((app / name).stat().st_mtime_ns == original_times[name] for name in files if name != "modules/x64/d3d/d3dcompiler_47.dll")
        assert subprocess.run([str(damaged), "--prepare-only", str(temporary / "empty profile")]).returncode == 1
        assert sentinel.read_text() == "keep my profile"
        for name, path in files.items():
            assert digest(path) == hashes[name], "source changed during packaging"
        output.parent.mkdir(parents=True, exist_ok=True)
        with candidate.open("rb") as source, output.open("xb") as destination:
            shutil.copyfileobj(source, destination)
    print(output)
    print(f"{output.stat().st_size / 1024 / 1024:.1f} MiB; embedded payload, initial setup, reuse without extraction, repair and profile preservation checked")


if __name__ == "__main__":
    main()
