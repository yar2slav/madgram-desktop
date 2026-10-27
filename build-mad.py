import argparse
import os
from pathlib import Path
import re
import runpy
import shutil
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--tests", action="store_true")
    parser.add_argument("--config", choices=("Debug", "Release"), default="Debug")
    parser.add_argument("--qt-prefix", type=Path)
    parser.add_argument("--build-number", type=int, default=0)
    parser.add_argument("--launcher", type=Path)
    parser.add_argument("--build-dir", type=Path)
    args = parser.parse_args()
    if not 1 <= args.jobs <= 32:
        raise SystemExit("jobs must be between 1 and 32")
    root = Path(__file__).resolve().parent.parent
    original = root / "tdesktop/out"
    build = original / "release-build" if args.config == "Release" else original
    if args.build_dir:
        build = args.build_dir.resolve()
    environment = runpy.run_path(str(root / "mad/prepare-mad-release.py"))["build_environment"]()
    generators = {"17": "Visual Studio 17 2022", "18": "Visual Studio 18 2026"}
    generator = generators.get(environment.get("VISUALSTUDIOVERSION", "17.0").split(".")[0])
    if not generator:
        raise SystemExit("unsupported visual studio version")
    if args.launcher:
        generator = "Ninja Multi-Config"
    environment["CMAKE_GENERATOR"] = generator
    environment["LINK"] = "/PDBPAGESIZE:8192"
    cmake = shutil.which("cmake", path=environment["PATH"])

    def run(command):
        return subprocess.run(list(map(str, command)), cwd=root, env=environment)

    def cache_values(directory):
        path = directory / "CMakeCache.txt"
        keys = {"TDESKTOP_API_ID", "TDESKTOP_API_HASH", "DESKTOP_APP_DISABLE_AUTOUPDATE", "TELE_BUILD", "MAD_BUILD_TESTS", "Qt6_DIR"}
        if not path.exists():
            return {}
        return {line.split(":", 1)[0]: line.split("=", 1)[1].strip() for line in path.read_text(encoding="utf-8").splitlines() if "=" in line and line.split(":", 1)[0] in keys}

    options = cache_values(build)
    qt = args.qt_prefix.resolve() if args.qt_prefix else root / "Libraries/win64/Qt-6.11.2-release"
    configure = [cmake, "-S", root / "tdesktop", "-B", build, "-DDESKTOP_APP_DISABLE_AUTOUPDATE=ON", f"-DTELE_BUILD={args.build_number}"]
    if args.tests:
        configure.append("-DMAD_BUILD_TESTS=ON")
    if args.config == "Release":
        if not (qt / "lib/Qt6Core.lib").exists():
            raise SystemExit("run prepare-mad-release.py first")
        configure += ["-DCMAKE_CONFIGURATION_TYPES=Release", f"-DMAD_QT_PREFIX={qt.as_posix()}", f"-DCMAKE_PREFIX_PATH={qt.as_posix()}", f"-DQt6_DIR={qt.as_posix()}/lib/cmake/Qt6", f"-DQT_DIR={qt.as_posix()}/lib/cmake/Qt6", "-Dqt_requested=6.11.2"]
    if not options:
        credentials = cache_values(original)
        if os.environ.get("GITHUB_ACTIONS") == "true":
            credentials = {name: os.environ.get(name, "") for name in ("TDESKTOP_API_ID", "TDESKTOP_API_HASH")}
        api_id, api_hash = credentials.get("TDESKTOP_API_ID", ""), credentials.get("TDESKTOP_API_HASH", "")
        if not re.fullmatch(r"[1-9][0-9]*", api_id) or not re.fullmatch(r"[a-fA-F0-9]{32}", api_hash):
            raise SystemExit("run configure-mad.py first")
        package = "Microsoft.Web.WebView2"
        if (original / "packages" / package).exists():
            shutil.copytree(original / "packages" / package, build / "packages" / package, dirs_exist_ok=True)
        else:
            result = run([root / "ThirdParty/NuGet/nuget.exe", "install", package, "-Version", "1.0.1901.177", "-ExcludeVersion", "-NonInteractive", "-Source", "https://api.nuget.org/v3/index.json", "-OutputDirectory", build / "packages"])
            if result.returncode:
                return result.returncode
        with tempfile.TemporaryDirectory(prefix="mad-configure-") as temporary:
            preload = Path(temporary) / "credentials.cmake"
            preload.write_text(f'set(TDESKTOP_API_ID "{api_id}" CACHE STRING "" FORCE)\nset(TDESKTOP_API_HASH "{api_hash}" CACHE STRING "" FORCE)\n', encoding="utf-8")
            if args.launcher:
                launcher = args.launcher.resolve().as_posix()
                layout = ["-G", generator, f"-DCMAKE_C_COMPILER_LAUNCHER={launcher}", f"-DCMAKE_CXX_COMPILER_LAUNCHER={launcher}", "-DCMAKE_MSVC_DEBUG_INFORMATION_FORMAT="]
            else:
                layout = ["-G", generator, "-A", "x64", "-T", "v143,version=14.44"]
            result = run(configure + layout + ["-C", preload])
    elif options.get("DESKTOP_APP_DISABLE_AUTOUPDATE") != "ON" or options.get("TELE_BUILD") != str(args.build_number) or (args.tests and options.get("MAD_BUILD_TESTS") != "ON") or (args.config == "Release" and options.get("Qt6_DIR") != f"{qt.as_posix()}/lib/cmake/Qt6"):
        result = run(configure)
    else:
        result = subprocess.CompletedProcess([], 0)
    if result.returncode:
        return result.returncode
    targets = ["mad_registry_tests", "mad_history_crypto_tests", "mad_links_tests"] if args.tests else ["Telegram"]
    command = [cmake, "--build", build, "--config", args.config, "--target", *targets, "--parallel", args.jobs]
    if not args.launcher:
        command += ["--", f"/p:CL_MPCount={args.jobs}"]
    result = run(command)
    if result.returncode == 0 and args.launcher and not args.tests:
        result = run(["python", root / "mad/ci/ccache-dated.py", build, args.config, "Telegram"])
    if result.returncode == 0 and args.tests:
        for target in targets:
            result = run([build / args.config / f"{target}.exe"])
            if result.returncode:
                break
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
