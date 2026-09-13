"""Small, typed Win32 adapter for one foreground scrolling target."""
import atexit
import ctypes
import time
from ctypes import wintypes as w


def release_cursor_clip():
    """Best-effort emergency release for shutdown/cancellation paths."""
    try:
        api = ctypes.WinDLL("user32", use_last_error=True)
        api.ClipCursor.argtypes = [ctypes.POINTER(w.RECT)]
        api.ClipCursor.restype = w.BOOL
        api.ClipCursor(None)
    except Exception:
        pass


atexit.register(release_cursor_clip)


class MouseInput(ctypes.Structure):
    _fields_ = [("dx", w.LONG), ("dy", w.LONG), ("mouseData", w.DWORD),
                ("dwFlags", w.DWORD), ("time", w.DWORD), ("extra", ctypes.c_size_t)]


class KeyboardInput(ctypes.Structure):
    _fields_ = [("vk", w.WORD), ("scan", w.WORD), ("flags", w.DWORD),
                ("time", w.DWORD), ("extra", ctypes.c_size_t)]


class InputUnion(ctypes.Union):
    _fields_ = [("mi", MouseInput), ("ki", KeyboardInput)]


class Input(ctypes.Structure):
    _fields_ = [("type", w.DWORD), ("data", InputUnion)]


class ScrollTarget:
    def __init__(self, rect):
        self.api = ctypes.WinDLL("user32", use_last_error=True)
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        for name, args, result in (
            ("WindowFromPoint", [w.POINT], w.HWND),
            ("GetAncestor", [w.HWND, w.UINT], w.HWND),
            ("GetForegroundWindow", [], w.HWND),
            ("SetForegroundWindow", [w.HWND], w.BOOL),
            ("BringWindowToTop", [w.HWND], w.BOOL),
            ("SetFocus", [w.HWND], w.HWND),
            ("GetWindowThreadProcessId", [w.HWND, ctypes.POINTER(w.DWORD)], w.DWORD),
            ("AttachThreadInput", [w.DWORD, w.DWORD, w.BOOL], w.BOOL),
            ("GetWindowRect", [w.HWND, ctypes.POINTER(w.RECT)], w.BOOL),
            ("IsWindow", [w.HWND], w.BOOL), ("IsIconic", [w.HWND], w.BOOL),
            ("GetCursorPos", [ctypes.POINTER(w.POINT)], w.BOOL),
            ("SetCursorPos", [ctypes.c_int, ctypes.c_int], w.BOOL),
            ("ClipCursor", [ctypes.POINTER(w.RECT)], w.BOOL),
            ("GetAsyncKeyState", [ctypes.c_int], ctypes.c_short),
            ("SendInput", [w.UINT, ctypes.POINTER(Input), ctypes.c_int], w.UINT),
        ):
            fn = getattr(self.api, name)
            fn.argtypes, fn.restype = args, result
        self.kernel.GetCurrentThreadId.argtypes = []
        self.kernel.GetCurrentThreadId.restype = w.DWORD
        self.point = (rect.center().x(), rect.center().y())
        self.scroll_hwnd = self.api.WindowFromPoint(w.POINT(*self.point))
        self.hwnd = self.api.GetAncestor(self.scroll_hwnd, 2)
        if not self.hwnd:
            raise RuntimeError("No scrolling window found in the selected region.")
        for x, y in ((rect.left(), rect.top()), (rect.right(), rect.top()),
                     (rect.left(), rect.bottom()), (rect.right(), rect.bottom())):
            if self.root_at(x, y) != self.hwnd:
                raise RuntimeError("Select content inside a single window.")
        self.bounds = self.window_rect()
        self.original_cursor = self.cursor()
        self._cursor_clipped = False

    def root_at(self, x, y):
        return self.api.GetAncestor(self.api.WindowFromPoint(w.POINT(x, y)), 2)

    def window_rect(self):
        r = w.RECT()
        if not self.api.GetWindowRect(self.hwnd, ctypes.byref(r)):
            raise RuntimeError("The target window is no longer available.")
        return r.left, r.top, r.right, r.bottom

    def cursor(self):
        p = w.POINT()
        if not self.api.GetCursorPos(ctypes.byref(p)):
            raise RuntimeError("Cannot read the pointer position.")
        return p.x, p.y

    def activate(self):
        current_thread = self.kernel.GetCurrentThreadId()
        target_thread = self.api.GetWindowThreadProcessId(self.hwnd, None)
        foreground = self.api.GetForegroundWindow()
        foreground_thread = self.api.GetWindowThreadProcessId(foreground, None)
        attached = []
        try:
            for thread in {target_thread, foreground_thread}:
                if (thread and thread != current_thread
                        and self.api.AttachThreadInput(current_thread, thread, True)):
                    attached.append(thread)
            self.api.BringWindowToTop(self.hwnd)
            self.api.SetForegroundWindow(self.hwnd)
            self.api.SetFocus(self.scroll_hwnd)
        finally:
            for thread in reversed(attached):
                self.api.AttachThreadInput(current_thread, thread, False)
        if not self.api.SetCursorPos(*self.point):
            raise RuntimeError("Cannot move the pointer to the capture region.")
        self.lock_cursor()
        deadline = time.monotonic() + 0.6
        while self.api.GetForegroundWindow() != self.hwnd and time.monotonic() < deadline:
            self.api.SetForegroundWindow(self.hwnd)
            time.sleep(0.04)
        if self.api.GetForegroundWindow() != self.hwnd:
            raise RuntimeError("Windows could not activate the selected window.")

    def lock_cursor(self):
        x, y = self.point
        bounds = w.RECT(x, y, x + 1, y + 1)
        if not self.api.ClipCursor(ctypes.byref(bounds)):
            raise RuntimeError("Windows could not lock the pointer for scrolling.")
        self._cursor_clipped = True

    def release_cursor(self):
        if self._cursor_clipped:
            self.api.ClipCursor(None)
            self._cursor_clipped = False

    def validate(self):
        if (not self.api.IsWindow(self.hwnd) or self.api.IsIconic(self.hwnd)
                or self.window_rect() != self.bounds
                or self.api.GetForegroundWindow() != self.hwnd):
            raise RuntimeError("Capture stopped because the target window changed.")
        x, y = self.cursor()
        if abs(x-self.point[0]) > 12 or abs(y-self.point[1]) > 12:
            raise RuntimeError("Capture stopped because the pointer moved. Keeping the captured portion.")
        if self.root_at(x, y) != self.hwnd:
            raise RuntimeError("Another window is covering the scrolling target.")

    def scroll(self, notches=1):
        self.validate()
        if any(self.api.GetAsyncKeyState(vk) & 0x8000 for vk in (0x10, 0x11, 0x12, 0x5B, 0x5C)):
            raise RuntimeError("Release modifier keys before scrolling.")
        event = Input(type=0, data=InputUnion(mi=MouseInput(
            mouseData=(-120 * notches) & 0xffffffff, dwFlags=0x0800)))
        if self.api.SendInput(1, ctypes.byref(event), ctypes.sizeof(Input)) != 1:
            raise RuntimeError("Windows blocked scrolling. Check the target application's permissions.")

    def restore_cursor(self):
        self.release_cursor()
        # If cancellation already released the clip, do not override a pointer
        # the user deliberately moved while the result was being assembled.
        if self.cursor() == self.point:
            self.api.SetCursorPos(*self.original_cursor)
