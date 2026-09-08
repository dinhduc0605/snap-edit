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
_COINIT_APARTMENTTHREADED = 0x2
_CLSCTX_INPROC_SERVER = 0x1
_VT_LPWSTR = 31


class _Guid(ctypes.Structure):
    """Minimal GUID structure used by the Shell COM interfaces below."""

    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]

    @classmethod
    def from_string(cls, value: str):
        import uuid

        parsed = uuid.UUID(value)
        return cls(
            parsed.time_low,
            parsed.time_mid,
            parsed.time_hi_version,
            (ctypes.c_ubyte * 8).from_buffer_copy(parsed.bytes[8:]),
        )


class _PropertyKey(ctypes.Structure):
    _fields_ = [("fmtid", _Guid), ("pid", wintypes.DWORD)]


class _PropVariantValue(ctypes.Union):
    _fields_ = [
        ("pwszVal", wintypes.LPWSTR),
        ("_padding", ctypes.c_byte * 16),
    ]


class _PropVariant(ctypes.Structure):
    _fields_ = [
        ("vt", wintypes.USHORT),
        ("wReserved1", wintypes.USHORT),
        ("wReserved2", wintypes.USHORT),
        ("wReserved3", wintypes.USHORT),
        ("value", _PropVariantValue),
    ]


_CLSID_SHELL_LINK = _Guid.from_string("00021401-0000-0000-C000-000000000046")
_IID_ISHELL_LINK_W = _Guid.from_string("000214F9-0000-0000-C000-000000000046")
_IID_IPERSIST_FILE = _Guid.from_string("0000010B-0000-0000-C000-000000000046")
_IID_IPROPERTY_STORE = _Guid.from_string("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99")
_PKEY_APP_USER_MODEL_ID = _PropertyKey(
    _Guid.from_string("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3"), 5,
)


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


def _notification_shortcut_command() -> tuple[Path, str, Path]:
    """Return the target, arguments, and working directory for SnapEdit."""
    if getattr(sys, "frozen", False):
        executable = Path(sys.executable).resolve()
        return executable, "", executable.parent

    python_executable = Path(sys.executable).resolve()
    pythonw_executable = python_executable.with_name("pythonw.exe")
    if pythonw_executable.exists():
        python_executable = pythonw_executable
    main_script = Path(__file__).resolve().parent / "main.py"
    return python_executable, subprocess.list2cmdline([str(main_script)]), main_script.parent


def _com_method(interface, index, result_type, *arg_types):
    """Get one method from a COM interface vtable."""
    vtable = ctypes.cast(
        interface, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)),
    ).contents
    method_type = ctypes.WINFUNCTYPE(result_type, ctypes.c_void_p, *arg_types)
    return method_type(vtable[index])


def _com_call(interface, index, result_type, arg_types, *args):
    return _com_method(interface, index, result_type, *arg_types)(interface, *args)


def _release_com_interface(interface):
    if interface:
        _com_call(interface, 2, wintypes.ULONG, ())


def _query_com_interface(interface, interface_id):
    result = ctypes.c_void_p()
    status = _com_call(
        interface,
        0,
        ctypes.c_long,
        (ctypes.POINTER(_Guid), ctypes.POINTER(ctypes.c_void_p)),
        ctypes.byref(interface_id),
        ctypes.byref(result),
    )
    if status < 0:
        return None
    return result


def _create_notification_shortcut(
    shortcut_path: Path,
    app_user_model_id: str,
    app_name: str,
    icon_path: Path,
) -> bool:
    """Create the Start-menu shortcut Windows uses to identify toast senders."""
    ole32 = ctypes.OleDLL("ole32")
    initialized = ole32.CoInitializeEx(None, _COINIT_APARTMENTTHREADED) >= 0
    shell_link = None
    property_store = None
    persist_file = None
    try:
        target, arguments, working_directory = _notification_shortcut_command()
        result = ctypes.c_void_p()
        status = ole32.CoCreateInstance(
            ctypes.byref(_CLSID_SHELL_LINK),
            None,
            _CLSCTX_INPROC_SERVER,
            ctypes.byref(_IID_ISHELL_LINK_W),
            ctypes.byref(result),
        )
        if status < 0:
            return False
        shell_link = result

        # IShellLinkW: SetPath, SetArguments, SetWorkingDirectory,
        # SetDescription, SetIconLocation.
        calls = (
            (20, (wintypes.LPCWSTR,), str(target)),
            (11, (wintypes.LPCWSTR,), arguments),
            (9, (wintypes.LPCWSTR,), str(working_directory)),
            (7, (wintypes.LPCWSTR,), app_name),
            (17, (wintypes.LPCWSTR, ctypes.c_int), str(icon_path), 0),
        )
        for index, arg_types, *args in calls:
            if _com_call(shell_link, index, ctypes.c_long, arg_types, *args) < 0:
                return False

        property_store = _query_com_interface(shell_link, _IID_IPROPERTY_STORE)
        if not property_store:
            return False
        app_id_buffer = ctypes.create_unicode_buffer(app_user_model_id)
        app_id = _PropVariant()
        app_id.vt = _VT_LPWSTR
        app_id.value.pwszVal = ctypes.cast(app_id_buffer, wintypes.LPWSTR)
        status = _com_call(
            property_store,
            6,  # IPropertyStore::SetValue
            ctypes.c_long,
            (ctypes.POINTER(_PropertyKey), ctypes.POINTER(_PropVariant)),
            ctypes.byref(_PKEY_APP_USER_MODEL_ID),
            ctypes.byref(app_id),
        )
        if status < 0 or _com_call(
            property_store, 7, ctypes.c_long, ()  # IPropertyStore::Commit
        ) < 0:
            return False

        persist_file = _query_com_interface(shell_link, _IID_IPERSIST_FILE)
        if not persist_file:
            return False
        return _com_call(
            persist_file,
            6,  # IPersistFile::Save
            ctypes.c_long,
            (wintypes.LPCWSTR, wintypes.BOOL),
            str(shortcut_path),
            True,
        ) >= 0
    except OSError:
        return False
    finally:
        _release_com_interface(persist_file)
        _release_com_interface(property_store)
        _release_com_interface(shell_link)
        if initialized:
            ole32.CoUninitialize()


def ensure_notification_identity(
    app_user_model_id: str,
    app_name: str,
    icon_path: Path,
) -> bool:
    """Install/update SnapEdit's per-user Start-menu notification identity.

    Windows uses the Start-menu shortcut associated with an AppUserModelID to
    render the notification header and its app icon. This is deliberately
    separate from startup registration, so users do not need to enable
    "Start with Windows" to receive a correctly branded notification.
    """
    if not startup_is_supported() or not icon_path.is_file():
        return False
    app_data = os.environ.get("APPDATA")
    if not app_data:
        return False
    shortcut_path = (
        Path(app_data) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
        / f"{app_name}.lnk"
    )
    try:
        shortcut_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False
    return _create_notification_shortcut(
        shortcut_path, app_user_model_id, app_name, icon_path.resolve(),
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
