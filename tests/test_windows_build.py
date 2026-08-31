"""Build isolation and entry-point checks; no GUI or executable is launched."""
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import bootstrap
from scripts.build_windows import clean_environment, verify_dll_origins, version_resource, windows_directory


class WindowsBuildTests(unittest.TestCase):
    def test_system_directory_handles_windows_environment_key_case(self):
        for key in ("SYSTEMROOT", "SystemRoot"):
            with self.subTest(key=key):
                self.assertEqual(windows_directory({key: "D:/Windows"}), Path("D:/Windows"))

    def test_build_environment_excludes_foreign_dll_and_plugin_paths(self):
        source = {
            "PATH": "C:/third-party/poppler;C:/third-party/conda",
            "SystemRoot": "C:/Windows",
            "PYTHONPATH": "C:/foreign-python",
            "PYTHONHOME": "C:/foreign-home",
            "QT_PLUGIN_PATH": "C:/foreign-qt/plugins",
            "QT_QPA_PLATFORM_PLUGIN_PATH": "C:/foreign-qt/platforms",
            "QT_QPA_PLATFORM": "offscreen",
            "QML2_IMPORT_PATH": "C:/foreign-qml2",
            "QML_IMPORT_PATH": "C:/foreign-qml",
            "TEMP": "C:/Temp",
        }
        original = dict(source)
        qt = SimpleNamespace(origin="C:/python/site-packages/PyQt6/__init__.py")
        with patch("scripts.build_windows.importlib.util.find_spec", return_value=qt):
            env = clean_environment(source)

        self.assertEqual(source, original)
        self.assertEqual(env["TEMP"], source["TEMP"])
        self.assertNotIn("third-party", env["PATH"])
        paths = env["PATH"].split(os.pathsep)
        self.assertEqual(paths[0], str(Path(qt.origin).parent / "Qt6" / "bin"))
        self.assertIn(str(Path("C:/Windows/System32")), paths)
        for key in original.keys() - {"PATH", "SystemRoot", "TEMP"}:
            self.assertNotIn(key, env)

    def test_dll_guard_rejects_icu_including_nested_and_mixed_case_names(self):
        for name in ("icuuc.dll", "ICUDT78.DLL", "PyQt6/Qt6/bin/icuin.dll",
                     "PyQt6\\Qt6\\bin\\icuuc.dll"):
            with self.subTest(name=name), self.assertRaisesRegex(RuntimeError, "Windows system ICU"):
                verify_dll_origins([(name, "C:/poppler/" + name, "BINARY")])

    def test_dll_guard_allows_normal_qt_and_python_dependencies(self):
        verify_dll_origins([
            ("PyQt6/Qt6/bin/Qt6Core.dll", "C:/python/Qt6Core.dll", "BINARY"),
            ("VCRUNTIME140.dll", "C:/python/VCRUNTIME140.dll", "BINARY"),
            ("python314.dll", "C:/python/python314.dll", "BINARY"),
        ])

    def test_version_resource_uses_release_version_without_v_prefix(self):
        resource = version_resource("v1.2.3")
        self.assertIn("filevers=(1, 2, 3, 0)", resource)
        self.assertIn("ProductVersion', '1.2.3.0'", resource)

    def test_version_resource_rejects_non_release_version(self):
        with self.assertRaisesRegex(ValueError, "X.Y.Z"):
            version_resource("release-1.2.3")

    def test_self_test_entry_point_runs_before_importing_application(self):
        smoke = SimpleNamespace(run=Mock(return_value=1))
        app = SimpleNamespace(main=Mock())
        with patch.object(bootstrap.sys, "argv", ["SnapEdit.exe", "--self-test-report", "result.json"]), \
                patch.dict("sys.modules", {"smoke_test": smoke, "main": app}):
            self.assertEqual(bootstrap.main(), 1)
        smoke.run.assert_called_once_with("result.json")
        app.main.assert_not_called()

    def test_normal_entry_point_starts_application(self):
        smoke = SimpleNamespace(run=Mock())
        app = SimpleNamespace(main=Mock())
        with patch.object(bootstrap.sys, "argv", ["SnapEdit.exe"]), \
                patch.dict("sys.modules", {"smoke_test": smoke, "main": app}):
            self.assertEqual(bootstrap.main(), 0)
        app.main.assert_called_once_with()
        smoke.run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
