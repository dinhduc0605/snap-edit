"""
Global hotkey manager for SnapEdit.
Uses pynput to listen for system-wide keyboard shortcuts and
emits PyQt6 signals so the main application can react.
"""
import logging
from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal

from pynput.keyboard import GlobalHotKeys

from settings.config import Config

logger = logging.getLogger(__name__)

# Modifier keys that must be wrapped in angle brackets for pynput
_PYNPUT_MODIFIERS = {
    "ctrl": "<ctrl>",
    "control": "<ctrl>",
    "alt": "<alt>",
    "shift": "<shift>",
    "cmd": "<cmd>",
    "win": "<cmd>",
    "super": "<cmd>",
}


class HotkeyManager(QObject):
    """Manages global hotkeys using *pynput* and bridges them to Qt signals.

    Signals
    -------
    fullscreen_triggered
        Emitted when the fullscreen capture hotkey is pressed.
    region_triggered
        Emitted when the region capture hotkey is pressed.
    scroll_triggered
        Emitted when the scroll capture hotkey is pressed.
    """

    fullscreen_triggered = pyqtSignal()
    region_triggered = pyqtSignal()
    timed_region_triggered = pyqtSignal()

    def __init__(self, config: Config, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._config = config
        self._listener: Optional[GlobalHotKeys] = None

    # ────────────────────────────────────────────────────────────────
    #  Public API
    # ────────────────────────────────────────────────────────────────
    def start(self):
        """Build a hotkey listener from the current config and start it.

        If a listener is already running it will be stopped first.
        """
        self.stop()

        hotkeys = self._config.hotkeys
        bindings: dict[str, callable] = {}

        self._register(bindings, hotkeys.get("fullscreen", ""),
                       self.fullscreen_triggered, "fullscreen")
        self._register(bindings, hotkeys.get("region", ""),
                       self.region_triggered, "region")
        self._register(bindings, hotkeys.get("timed_region", ""),
                       self.timed_region_triggered, "timed region")

        if not bindings:
            logger.warning("No valid hotkeys configured – listener not started.")
            return

        try:
            self._listener = GlobalHotKeys(bindings)
            self._listener.daemon = True
            self._listener.start()
            logger.info("Global hotkey listener started with %d binding(s).", len(bindings))
        except Exception:
            logger.exception("Failed to start global hotkey listener.")
            self._listener = None

    def stop(self):
        """Stop the current hotkey listener if one is running."""
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:
                logger.exception("Error while stopping hotkey listener.")
            finally:
                self._listener = None
                logger.info("Global hotkey listener stopped.")

    def reload(self, config: Config):
        """Replace the config and restart the listener.

        Parameters
        ----------
        config : Config
            The new (or refreshed) configuration instance.
        """
        self._config = config
        self.start()

    # ────────────────────────────────────────────────────────────────
    #  Internals
    # ────────────────────────────────────────────────────────────────
    def _register(self, bindings: dict, hotkey_str: str,
                  signal: pyqtSignal, label: str):
        """Parse *hotkey_str* and add it to *bindings* if valid."""
        if not hotkey_str or not hotkey_str.strip():
            logger.debug("Hotkey for '%s' is empty – skipped.", label)
            return

        try:
            pynput_str = self._to_pynput(hotkey_str)
        except ValueError as exc:
            logger.warning("Invalid hotkey '%s' for '%s': %s", hotkey_str, label, exc)
            return

        # Wrap signal.emit in a plain function (pynput calls from a worker
        # thread, but pyqtSignal.emit is thread‑safe).
        bindings[pynput_str] = signal.emit
        logger.debug("Registered hotkey '%s' (%s) for '%s'.", hotkey_str, pynput_str, label)

    @staticmethod
    def _to_pynput(hotkey_str: str) -> str:
        """Convert a human‑readable hotkey string to pynput format.

        Examples
        --------
        >>> HotkeyManager._to_pynput('ctrl+shift+f')
        '<ctrl>+<shift>+f'
        >>> HotkeyManager._to_pynput('Alt+S')
        '<alt>+s'

        Raises
        ------
        ValueError
            If *hotkey_str* contains no valid key tokens.
        """
        parts = [p.strip().lower() for p in hotkey_str.split("+") if p.strip()]
        if not parts:
            raise ValueError("Empty hotkey string.")

        converted: list[str] = []
        for part in parts:
            if part in _PYNPUT_MODIFIERS:
                converted.append(_PYNPUT_MODIFIERS[part])
            else:
                # Regular key – leave as‑is (single char or special name)
                converted.append(part)

        return "+".join(converted)
