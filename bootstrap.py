"""Executable entry point, with a non-interactive frozen-app smoke test."""
import sys


def main():
    # Run before importing Qt so DLL/plugin failures can be reported without
    # the windowed PyInstaller error dialog blocking automated verification.
    if len(sys.argv) == 3 and sys.argv[1] == "--self-test-report":
        from smoke_test import run
        return run(sys.argv[2])

    from main import main as run_app
    run_app()
    return 0


if __name__ == "__main__":
    sys.exit(main())
