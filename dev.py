"""Run SnapEdit in development mode with automatic restart on source changes.

Usage:
    python dev.py

This is intentionally dependency-free.  It watches the application's Python
source files and restarts ``main.py`` after a short quiet period whenever a
file is saved.  Press Ctrl+C in this terminal to stop both the watcher and
SnapEdit.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parent
MAIN_FILE = ROOT / "main.py"
WATCHED_SUFFIXES = {".py"}
IGNORED_DIRECTORIES = {
    ".git", "__pycache__", ".pytest_cache", ".venv", "venv",
    "build", "dist", "tests", "vendor",
}
QUIET_PERIOD_SECONDS = 0.35


def source_snapshot() -> dict[Path, tuple[int, int]]:
    """Return stable metadata for the source files relevant to the app."""
    snapshot: dict[Path, tuple[int, int]] = {}
    for directory, subdirectories, filenames in os.walk(ROOT):
        subdirectories[:] = [
            name for name in subdirectories if name not in IGNORED_DIRECTORIES
        ]
        base = Path(directory)
        for filename in filenames:
            path = base / filename
            if path.suffix.lower() not in WATCHED_SUFFIXES:
                continue
            try:
                stat = path.stat()
            except OSError:
                # A save can briefly replace a file between os.walk and stat.
                continue
            snapshot[path] = (stat.st_mtime_ns, stat.st_size)
    return snapshot


def start_app() -> subprocess.Popen:
    """Start the app with the same interpreter that launched this watcher."""
    print(f"[dev] Starting SnapEdit with {sys.executable}", flush=True)
    return subprocess.Popen([sys.executable, str(MAIN_FILE)], cwd=ROOT)


def stop_app(process: subprocess.Popen | None) -> None:
    """Stop a running child process without leaving a second tray instance."""
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run SnapEdit and restart it automatically after source edits."
    )
    parser.add_argument(
        "--interval", type=float, default=0.25,
        help="File polling interval in seconds (default: 0.25).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    interval = max(0.05, args.interval)
    snapshot = source_snapshot()
    process = start_app()
    changed_at: float | None = None
    exit_reported = False

    print("[dev] Watching Python source files. Press Ctrl+C to stop.", flush=True)
    try:
        while True:
            time.sleep(interval)
            current_snapshot = source_snapshot()
            if current_snapshot != snapshot:
                snapshot = current_snapshot
                changed_at = time.monotonic()

            if (
                changed_at is not None
                and time.monotonic() - changed_at >= QUIET_PERIOD_SECONDS
            ):
                print("[dev] Source change detected; restarting SnapEdit...", flush=True)
                stop_app(process)
                process = start_app()
                changed_at = None
                exit_reported = False

            if process.poll() is not None and not exit_reported:
                print(
                    "[dev] SnapEdit stopped. Save a source file to start it again, "
                    "or press Ctrl+C to exit the watcher.",
                    flush=True,
                )
                exit_reported = True
    except KeyboardInterrupt:
        print("\n[dev] Stopping development watcher...", flush=True)
    finally:
        stop_app(process)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
