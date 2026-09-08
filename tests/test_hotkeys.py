"""Hotkey parsing, dispatch and registration lifecycle; no keyboard injection."""
import ctypes
from ctypes import wintypes
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from PyQt6.QtWidgets import QApplication
from hotkey.manager import HotkeyManager, MOD_NOREPEAT, WM_HOTKEY, parse_hotkey


class HotkeyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.api = SimpleNamespace(RegisterHotKey=Mock(return_value=True),
                                   UnregisterHotKey=Mock(return_value=True),
                                   VkKeyScanW=Mock(return_value=-1))
        self.config = SimpleNamespace(hotkeys={'fullscreen': 'alt+shift+1',
                                              'region': 'alt+shift+2'})
        with patch('hotkey.manager.windows_api', return_value=self.api):
            self.manager = HotkeyManager(self.config)
        self.events = []
        self.manager.fullscreen_triggered.connect(lambda: self.events.append('full'))
        self.manager.region_triggered.connect(lambda: self.events.append('region'))

    def tearDown(self):
        self.manager.stop()

    def test_settings_names_and_invalid_combinations(self):
        for text, expected in [('alt+shift+1', (5, 49)), ('Ctrl+F8', (2, 0x77)),
                               ('win+left', (8, 0x25)), ('ctrl+space', (2, 32))]:
            self.assertEqual(parse_hotkey(text, self.api), expected)
        for text in ('alt+shift', 'ctrl+f12', 'ctrl+k,ctrl+c', 'garbage'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_hotkey(text, self.api)

    def test_partial_combinations_and_wrong_key_cannot_dispatch(self):
        self.manager.start()
        identifier = next(iter(self.manager._bindings))
        for modifiers, vk in ((5, 0), (4, 49), (1, 49), (0, 49), (5, 50)):
            self.assertFalse(self.manager.dispatch(identifier, (vk << 16) | modifiers))
        self.assertEqual(self.events, [])
        self.assertTrue(self.manager.dispatch(identifier, (49 << 16) | 5))
        self.assertEqual(self.events, ['full'])
        for call in self.api.RegisterHotKey.call_args_list:
            self.assertTrue(call.args[2] & MOD_NOREPEAT)

    def test_native_message_routing_and_reload_rejects_old_events(self):
        self.manager.start()
        identifier = next(iter(self.manager._bindings))
        msg = wintypes.MSG()
        msg.message = WM_HOTKEY
        msg.wParam = identifier
        msg.lParam = (49 << 16) | 5
        self.assertEqual(self.manager._filter.nativeEventFilter(
            b'windows_dispatcher_MSG', ctypes.addressof(msg)), (True, 0))
        self.manager.reload(SimpleNamespace(hotkeys={'region': 'ctrl+f8'}))
        self.assertFalse(self.manager.dispatch(identifier, msg.lParam))
        self.api.UnregisterHotKey.assert_any_call(None, identifier)
        self.assertEqual(self.events, ['full'])
        self.manager.stop()
        self.manager.stop()
        self.assertEqual(self.manager._bindings, {})

    def test_conflict_is_reported_and_other_binding_remains_usable(self):
        self.api.RegisterHotKey.side_effect = [False, True]
        errors = []
        self.manager.registration_failed.connect(errors.append)
        with self.assertLogs('hotkey.manager', level='WARNING'):
            self.manager.start()
        self.assertEqual(len(errors), 1)
        self.assertIn('alt+shift+1', errors[0])
        identifier = next(iter(self.manager._bindings))
        self.assertTrue(self.manager.dispatch(identifier, (50 << 16) | 5))
        self.assertEqual(self.events, ['region'])
