"""Build with isolated DLL search paths, then run the finished executable.

Usage: python scripts/build_windows.py
Does not install packages or change the user's system PATH.
"""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]


def windows_directory(env):
    # os.environ normalizes Windows keys to uppercase; plain dicts do not.
    return Path(env.get("SYSTEMROOT") or env.get("SystemRoot") or "C:/Windows")


def clean_environment(source=None):
    env = dict(os.environ if source is None else source)
    windows = windows_directory(env)
    # Never search Poppler/Conda/Git/etc. for dependencies of Windows Qt.
    # In particular their icuuc.dll exports a different ABI to Windows ICU.
    qt = importlib.util.find_spec("PyQt6")
    qt_bin = Path(qt.origin).parent / "Qt6" / "bin" if qt else None
    paths = [qt_bin, Path(sys.executable).parent, Path(sys.base_prefix),
             Path(sys.base_prefix) / "DLLs", windows / "System32", windows]
    env["PATH"] = os.pathsep.join(dict.fromkeys(str(path) for path in paths if path))
    for key in ("PYTHONPATH", "PYTHONHOME", "QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH",
                "QT_QPA_PLATFORM", "QML2_IMPORT_PATH", "QML_IMPORT_PATH"):
        env.pop(key, None)
    return env


def verify_dll_origins(binaries):
    """Fail the build rather than ship a foreign ICU in place of Windows ICU."""
    for target, source, _kind in binaries:
        name = target.replace("\\", "/").rsplit("/", 1)[-1].lower()
        if name.startswith("icu") and name.endswith(".dll"):
            raise RuntimeError(
                f"Unexpected bundled Windows ICU dependency: {target} from {source}. "
                "Qt must use the Windows system ICU; build with a clean PATH."
            )


def verify_executable(executable, env, label):
    report_path = ROOT / "build" / f"smoke-{label}-{uuid.uuid4().hex}.json"
    result = subprocess.run(
        [str(executable), "--self-test-report", str(report_path)],
        cwd=executable.parent, env=env, timeout=45,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {}
    if result.returncode or not report.get("ok") or not report.get("frozen"):
        raise RuntimeError(f"Frozen smoke test failed ({label}, exit {result.returncode}): {report}")
    print(f"Smoke test passed ({label}): Qt {report['qt']}, {report.get('icu_path', '')}", flush=True)
    print(f"Report: {report_path}", flush=True)


def main():
    if sys.platform != "win32":
        raise SystemExit("This build targets Windows 11.")
    env = clean_environment()
    subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm", str(ROOT / "SnapEdit.spec")],
        cwd=ROOT, env=env, check=True,
    )
    executable = ROOT / "dist" / "SnapEdit.exe"
    # No Python/Qt locations on PATH: emulate an end-user installation.
    standalone_env = clean_environment()
    windows = windows_directory(standalone_env)
    standalone_env["PATH"] = os.pathsep.join((str(windows / "System32"), str(windows)))
    verify_executable(executable, standalone_env, "standalone")
    # Also test with the caller's original PATH, including any third-party ICU.
    inherited_env = dict(standalone_env)
    inherited_env["PATH"] = os.environ.get("PATH", standalone_env["PATH"])
    verify_executable(executable, inherited_env, "inherited-path")


if __name__ == "__main__":
    main()
