"""Windows startup registration and single-instance support."""

import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import subprocess
import sys


_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_RUN_VALUE_NAME = "SnapEdit"
_MUTEX_NAME = r"Local\SnapEdit.Application.Singleton"
_ERROR_ALREADY_EXISTS = 183


def startup_is_supported() -> bool:
    return os.name == "nt"


def startup_command() -> str:
    """Return the command Windows should run when the user signs in."""
    if getattr(sys, "frozen", False):
        return subprocess.list2cmdline([str(Path(sys.executable).resolve())])

    python_executable = Path(sys.executable).resolve()
    pythonw_executable = python_executable.with_name("pythonw.exe")
    if pythonw_executable.exists():
        python_executable = pythonw_executable
    main_script = Path(__file__).resolve().parent / "main.py"
    return subprocess.list2cmdline(
        [str(python_executable), str(main_script)]
    )


def is_startup_enabled() -> bool:
    if not startup_is_supported():
        return False

    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            _RUN_KEY,
            0,
            winreg.KEY_READ,
        ) as key:
            value, _ = winreg.QueryValueEx(key, _RUN_VALUE_NAME)
            return bool(value)
    except FileNotFoundError:
        return False


def set_startup_enabled(enabled: bool):
    """Add or remove the per-user SnapEdit startup registry value."""
    if not startup_is_supported():
        raise OSError("Start with Windows is only available on Windows.")

    import winreg

    if enabled:
        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER,
            _RUN_KEY,
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            winreg.SetValueEx(
                key,
                _RUN_VALUE_NAME,
                0,
                winreg.REG_SZ,
                startup_command(),
            )
        return

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            _RUN_KEY,
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            winreg.DeleteValue(key, _RUN_VALUE_NAME)
    except FileNotFoundError:
        pass


class SingleInstanceLock:
    """Keep a named Windows mutex alive for the lifetime of the process."""

    def __init__(self, name: str = _MUTEX_NAME):
        self._name = name
        self._handle = None

    def acquire(self) -> bool:
        if self._handle is not None:
            return True
        if os.name != "nt":
            self._handle = True
            return True

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        create_mutex = kernel32.CreateMutexW
        create_mutex.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
        create_mutex.restype = wintypes.HANDLE

        ctypes.set_last_error(0)
        handle = create_mutex(None, False, self._name)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        if ctypes.get_last_error() == _ERROR_ALREADY_EXISTS:
            close_handle = kernel32.CloseHandle
            close_handle.argtypes = [wintypes.HANDLE]
            close_handle.restype = wintypes.BOOL
            close_handle(handle)
            return False

        self._handle = handle
        return True

    def release(self):
        if self._handle is None:
            return
        if os.name == "nt" and self._handle is not True:
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            close_handle = kernel32.CloseHandle
            close_handle.argtypes = [wintypes.HANDLE]
            close_handle.restype = wintypes.BOOL
            close_handle(self._handle)
        self._handle = None

    def __enter__(self):
        if not self.acquire():
            raise RuntimeError("SnapEdit is already running.")
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.release()


def show_already_running_message():
    if os.name == "nt":
        ctypes.windll.user32.MessageBoxW(
            None,
            "SnapEdit is already running in the system tray.",
            "SnapEdit",
            0x40,
        )
