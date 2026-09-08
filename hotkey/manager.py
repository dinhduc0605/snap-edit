"""Windows-owned global hotkeys delivered through Qt's native event loop."""
import ctypes
from ctypes import wintypes
import itertools
import logging
import re
import weakref

from PyQt6.QtCore import QAbstractNativeEventFilter, QCoreApplication, QObject, Qt, pyqtSignal
from PyQt6.QtGui import QKeySequence

logger = logging.getLogger(__name__)
WM_HOTKEY = 0x0312
MOD_NOREPEAT = 0x4000
# Fresh IDs prevent queued events from activating a new binding after reload.
_IDS = itertools.count(0x1000)


def windows_api():
    api = ctypes.WinDLL('user32', use_last_error=True)
    api.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
    api.RegisterHotKey.restype = wintypes.BOOL
    api.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
    api.UnregisterHotKey.restype = wintypes.BOOL
    api.VkKeyScanW.argtypes = [wintypes.WCHAR]
    api.VkKeyScanW.restype = ctypes.c_short
    return api


def parse_hotkey(text, api):
    # Use the same key names as the Qt settings editor.
    text = text.strip()
    for alias in ('control', 'win', 'cmd', 'super'):
        text = re.sub(r'(?i)\b' + alias + r'\+',
                      'Ctrl+' if alias == 'control' else 'Meta+', text)
    sequence = QKeySequence.fromString(text, QKeySequence.SequenceFormat.PortableText)
    if sequence.count() != 1:
        raise ValueError('Choose one key combination.')
    combination = sequence[0]
    key = int(combination.key())
    modifiers = combination.keyboardModifiers()
    mask = 0
    for qt_modifier, native in ((Qt.KeyboardModifier.AltModifier, 1),
                                (Qt.KeyboardModifier.ControlModifier, 2),
                                (Qt.KeyboardModifier.ShiftModifier, 4),
                                (Qt.KeyboardModifier.MetaModifier, 8)):
        if modifiers & qt_modifier:
            mask |= native
    if modifiers & (Qt.KeyboardModifier.KeypadModifier | Qt.KeyboardModifier.GroupSwitchModifier):
        raise ValueError('Keypad and group-switch modifiers are unsupported.')
    named = {'Escape': 0x1B, 'Tab': 9, 'Backspace': 8, 'Return': 13, 'Enter': 13,
             'Insert': 0x2D, 'Delete': 0x2E, 'Pause': 0x13, 'Print': 0x2C,
             'Home': 0x24, 'End': 0x23, 'Left': 0x25, 'Up': 0x26,
             'Right': 0x27, 'Down': 0x28, 'PageUp': 0x21, 'PageDown': 0x22,
             'Space': 0x20}
    special = {int(getattr(Qt.Key, 'Key_' + name)): vk for name, vk in named.items()}
    if key == int(Qt.Key.Key_F12):
        raise ValueError('F12 is reserved by Windows.')
    if ord('A') <= key <= ord('Z') or ord('0') <= key <= ord('9'):
        vk = key
    elif int(Qt.Key.Key_F1) <= key <= int(Qt.Key.Key_F24):
        vk = 0x70 + key - int(Qt.Key.Key_F1)
    elif key in special:
        vk = special[key]
    elif 0x21 <= key <= 0xFFFF:
        translated = api.VkKeyScanW(chr(key))
        if translated == -1:
            raise ValueError('Key is unavailable on the current keyboard layout.')
        vk = translated & 0xFF
        shift_state = (translated >> 8) & 7
        mask |= (4 if shift_state & 1 else 0) | (2 if shift_state & 2 else 0) | (1 if shift_state & 4 else 0)
    else:
        raise ValueError('Unsupported key combination.')
    return mask, vk


class _HotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, owner):
        super().__init__()
        self.owner = weakref.ref(owner)

    def nativeEventFilter(self, event_type, message):
        if bytes(event_type) not in (b'windows_dispatcher_MSG', b'windows_generic_MSG'):
            return False, 0
        msg = wintypes.MSG.from_address(int(message))
        owner = self.owner()
        if owner is not None and msg.message == WM_HOTKEY and not msg.hWnd:
            return owner.dispatch(int(msg.wParam), int(msg.lParam)), 0
        return False, 0


class HotkeyManager(QObject):
    fullscreen_triggered = pyqtSignal()
    region_triggered = pyqtSignal()
    timed_region_triggered = pyqtSignal()
    ocr_triggered = pyqtSignal()
    registration_failed = pyqtSignal(str)

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self._config = config
        self._api = windows_api()
        self._bindings = {}
        self._filter = _HotkeyFilter(self)
        self._installed = False
        QCoreApplication.instance().aboutToQuit.connect(self.stop)

    def start(self):
        self.stop()
        app = QCoreApplication.instance()
        app.installNativeEventFilter(self._filter)
        self._installed = True
        errors = []
        for name in ('fullscreen', 'region', 'timed_region', 'ocr'):
            text = self._config.hotkeys.get(name, '')
            if not text.strip():
                continue
            try:
                modifiers, vk = parse_hotkey(text, self._api)
                identifier = next(_IDS)
                if identifier > 0xBFFF:
                    raise ValueError('Restart SnapEdit before changing hotkeys again.')
                if not self._api.RegisterHotKey(None, identifier, modifiers | MOD_NOREPEAT, vk):
                    raise ctypes.WinError(ctypes.get_last_error())
                self._bindings[identifier] = (modifiers, vk, getattr(self, name + '_triggered'))
            except (ValueError, OSError) as exc:
                errors.append(f'{name}: {text} — {exc}')
        if errors:
            message = '\n'.join(errors)
            logger.warning('Hotkey registration failed: %s', message)
            self.registration_failed.emit(message)

    def dispatch(self, identifier, packed_keys):
        binding = self._bindings.get(identifier)
        if binding is None:
            return False
        modifiers, vk, signal = binding
        if packed_keys & 0xFFFF != modifiers or (packed_keys >> 16) & 0xFFFF != vk:
            return False
        signal.emit()
        return True

    def stop(self):
        for identifier in self._bindings:
            self._api.UnregisterHotKey(None, identifier)
        self._bindings.clear()
        if self._installed:
            QCoreApplication.instance().removeNativeEventFilter(self._filter)
            self._installed = False

    def reload(self, config):
        self._config = config
        self.start()
