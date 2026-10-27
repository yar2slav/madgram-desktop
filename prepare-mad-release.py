import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parent.parent
LIBS = ROOT / "Libraries/win64"


def build_environment():
    vswhere = Path(os.environ["ProgramFiles(x86)"]) / "Microsoft Visual Studio/Installer/vswhere.exe"
    installation = subprocess.check_output([
        str(vswhere), "-latest", "-products", "*", "-requires",
        "Microsoft.VisualStudio.Component.VC.Tools.x86.x64", "-property", "installationPath",
    ], text=True).strip()
    if not installation:
        raise SystemExit("visual studio c++ build tools not found")
    vcvars = Path(installation) / "VC/Auxiliary/Build/vcvars64.bat"
    shell = os.environ.get("COMSPEC", "cmd.exe")
    with tempfile.TemporaryDirectory(prefix="mad-build-env-") as temporary:
        batch = Path(temporary) / "environment.cmd"
        batch.write_text(f'@call "{vcvars}" 10.0.26100.0 -vcvars_ver=14.44 >nul\n@if errorlevel 1 exit /b 1\n@set\n')
        output = subprocess.check_output([shell, "/d", "/c", str(batch)], text=True)
    environment = dict(os.environ)
    for line in output.splitlines():
        name, separator, value = line.partition("=")
        if separator and name:
            environment[name.upper()] = value
    additions = [ROOT / "ThirdParty/python/Scripts", ROOT / "ThirdParty/msys64/ucrt64/bin", ROOT / "ThirdParty/jom", ROOT / "ThirdParty/gyp"]
    environment["PATH"] = os.pathsep.join(map(str, additions)) + os.pathsep + environment["PATH"]
    environment["VSLANG"] = "1033"
    environment["LC_ALL"] = "C"
    environment["LANG"] = "C"
    environment["CMAKE_GENERATOR"] = "Ninja Multi-Config"
    environment["CMAKE_BUILD_PARALLEL_LEVEL"] = "4"
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return environment


def clone_source(source, destination, patches=()):
    marker = destination / ".mad-source-ready"
    if marker.exists():
        return
    if not (destination / ".git").exists():
        subprocess.run(["git", "clone", "--no-hardlinks", str(source), str(destination)], check=True)
        revision = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
        subprocess.run(["git", "-C", str(destination), "checkout", "--detach", revision], check=True)
    difference = subprocess.check_output(["git", "-C", str(source), "diff", "HEAD", "--binary", "--ignore-submodules=all"])
    if difference:
        check = subprocess.run(["git", "-C", str(destination), "apply", "--reverse", "--check", "-"], input=difference, capture_output=True)
        if check.returncode:
            subprocess.run(["git", "-C", str(destination), "apply", "--whitespace=nowarn", "-"], input=difference, check=True)
    for patch in patches:
        for name in re.findall(r"^\+\+\+ b/(.+)$", patch.read_text(encoding="utf-8"), re.MULTILINE):
            relative = Path(name.strip())
            if relative.is_absolute() or ".." in relative.parts:
                raise SystemExit("invalid patch path")
            original = source / relative
            target = destination / relative
            if original.is_file() and not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(original, target)
    marker.touch()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--stage", choices=("all", "libraries", "qt"), default="all")
    args = parser.parse_args()
    if not 1 <= args.jobs <= 32:
        raise SystemExit("jobs must be between 1 and 32")
    environment = build_environment()
    environment["CMAKE_BUILD_PARALLEL_LEVEL"] = str(args.jobs)

    def run(command, cwd=ROOT):
        command = list(map(str, command))
        command[0] = shutil.which(command[0], path=environment["PATH"]) or command[0]
        subprocess.run(command, cwd=cwd, env=environment, check=True)

    def build(folder, config="Release"):
        print(f"building {folder} ({config})", flush=True)
        run(["cmake", "--build", LIBS / folder, "--config", config, "--parallel", args.jobs])

    if args.stage in ("all", "libraries"):
        build("zlib")
        for original, alias in (("zlib/Release/libzs.lib", "zlib/Release/zlibstatic.lib"), ("zlib/contrib/minizip/Release/libminizips.lib", "zlib/contrib/minizip/Release/minizipstatic.lib")):
            if (LIBS / original).exists():
                shutil.copy2(LIBS / original, LIBS / alias)
        build("mozjpeg")
        openssl = LIBS / "openssl3/out"
        if not (openssl / "libcrypto.lib").exists() or not (openssl / "libssl.lib").exists():
            clone_source(LIBS / "openssl3", LIBS / "openssl3-release")
            openssl.mkdir(exist_ok=True)
            if not (openssl / "Makefile").exists():
                run(["perl", LIBS / "openssl3-release/Configure", "no-shared", "no-tests", "VC-WIN64A", "/FS"], openssl)
            run(["jom", f"-j{args.jobs}", "build_libs"], openssl)
        for folder in ("dav1d", "openh264"):
            source = LIBS / folder
            if not (source / "builddir-release/meson-private/coredata.dat").exists():
                flags = ["-Denable_tools=false", "-Denable_tests=false"] if folder == "dav1d" else []
                run(["meson", "setup", "--cross-file", "cross-file.txt", "--default-library=static", "--buildtype=release", "-Db_vscrt=mt", *flags, "builddir-release"], source)
            run(["meson", "compile", "-C", "builddir-release", "-j", args.jobs], source)
        for folder, config in (("rnnoise/out", "Release"), ("openal-soft/build", "RelWithDebInfo"), ("libavif", "Release"), ("libheif", "Release"), ("libjxl", "Release"), ("tg_angle/out", "Release"), ("tg_owt/out", "Release")):
            build(folder, config)
        tde2e = LIBS / "tde2e/out/Release"
        if not (tde2e / "CMakeCache.txt").exists():
            linker = f"/SAFESEH:NO Ws2_32.lib Gdi32.lib Advapi32.lib Crypt32.lib User32.lib {openssl.as_posix()}/libssl.lib"
            run(["cmake", "-S", LIBS / "tde2e", "-B", tde2e, "-DOPENSSL_FOUND=1", f"-DOPENSSL_INCLUDE_DIR={LIBS.as_posix()}/openssl3/include", f"-DOPENSSL_CRYPTO_LIBRARY={openssl.as_posix()}/libcrypto.lib", "-DZLIB_FOUND=1", f"-DZLIB_INCLUDE_DIR={LIBS.as_posix()}/zlib", f"-DZLIB_LIBRARIES={LIBS.as_posix()}/zlib/Release/libzs.lib", "-DCMAKE_CONFIGURATION_TYPES=Release", "-DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded$<$<CONFIG:Debug>:Debug>", "-DCMAKE_POLICY_DEFAULT_CMP0091=NEW", "-DCMAKE_C_FLAGS=/DZLIB_WINAPI", "-DCMAKE_CXX_FLAGS=/DZLIB_WINAPI", f"-DCMAKE_EXE_LINKER_FLAGS={linker}", f"-DCMAKE_SHARED_LINKER_FLAGS={linker}", "-DTD_ENABLE_MULTI_PROCESSOR_COMPILATION=ON", "-DTD_E2E_ONLY=ON"])
        build("tde2e/out/Release")
    if args.stage in ("all", "qt"):
        source = LIBS / "qt_6.11.2"
        release = LIBS / "qt_6.11.2-release"
        clone_source(source, release)
        for module in ("qtbase", "qtimageformats", "qtshadertools", "qtsvg"):
            patches = list((LIBS / f"patches/{module}_6.11.2").glob("**/*.patch"))
            if module == "qtbase":
                patches += list((LIBS / "qt6_windows7").glob("*.patch"))
            clone_source(source / module, release / module, patches)
        if not (release / "CMakeCache.txt").exists():
            options = [line for line in (source / "config.opt").read_text().splitlines() if line]
            options[options.index("-prefix") + 1] = str(LIBS / "Qt-6.11.2-release")
            options = ["-release" if option in ("-debug", "-debug-and-release") else option for option in options]
            if "-force-debug-info" not in options:
                options.insert(0, "-force-debug-info")
            environment["CMAKE_GENERATOR"] = "Ninja"
            run([os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", str(release / "configure.bat"), *options], release)
        build("qt_6.11.2-release", "RelWithDebInfo")
        run(["cmake", "--install", release, "--config", "RelWithDebInfo"])


if __name__ == "__main__":
    main()
