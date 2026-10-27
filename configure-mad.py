import getpass
import os
from pathlib import Path
import re
import subprocess
import tempfile


def main():
    root = Path(__file__).resolve().parent.parent
    vswhere = Path(os.environ["ProgramFiles(x86)"]) / "Microsoft Visual Studio/Installer/vswhere.exe"
    installation = subprocess.check_output([
        str(vswhere), "-latest", "-products", "*", "-requires",
        "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
        "-property", "installationPath",
    ], text=True).strip()
    if not installation:
        raise SystemExit("visual studio c++ build tools not found")
    subprocess.run([
        str(root / "ThirdParty/NuGet/nuget.exe"), "install", "Microsoft.Web.WebView2",
        "-Version", "1.0.1901.177", "-ExcludeVersion", "-NonInteractive",
        "-Source", "https://api.nuget.org/v3/index.json",
        "-OutputDirectory", str(root / "tdesktop/out/packages"),
    ], check=True)
    api_id = input("api_id: ").strip()
    api_hash = getpass.getpass("api_hash (hidden): ").strip()
    if not re.fullmatch(r"[1-9][0-9]*", api_id) or not re.fullmatch(r"[a-fA-F0-9]{32}", api_hash):
        raise SystemExit("invalid api_id or api_hash")
    vcvars = Path(installation) / "VC/Auxiliary/Build/vcvars64.bat"
    environment = os.environ.copy()
    environment["VSLANG"] = "1033"
    environment["CMAKE_GENERATOR"] = "Visual Studio 17 2022"
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    with tempfile.TemporaryDirectory(prefix="mad-configure-") as temporary:
        preload = Path(temporary) / "credentials.cmake"
        preload.write_text(
            f'set(TDESKTOP_API_ID "{api_id}" CACHE STRING "" FORCE)\n'
            f'set(TDESKTOP_API_HASH "{api_hash}" CACHE STRING "" FORCE)\n',
            encoding="utf-8",
        )
        command = (
            f'call "{vcvars}" 10.0.26100.0 -vcvars_ver=14.44 >nul && '
            f'call configure.bat x64 -C "{preload}" '
            '-D DESKTOP_APP_DISABLE_AUTOUPDATE=ON -D TELE_BUILD=0'
        )
        shell = os.environ.get("COMSPEC", "cmd.exe")
        result = subprocess.run(
            f'"{shell}" /d /s /c "{command}"',
            cwd=root / "tdesktop/Telegram",
            env=environment,
        )
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
