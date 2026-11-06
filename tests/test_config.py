import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fleetglint import config


class ConfigTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        patcher = mock.patch.dict(os.environ, {"XDG_STATE_HOME": str(self.dir / "state"),
                                               "XDG_CONFIG_HOME": str(self.dir / "config")})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def write(self, text):
        path = self.dir / "config.toml"
        path.write_text(text)
        return path

    def test_missing_file_gives_defaults(self):
        cfg = config.load()
        self.assertEqual(cfg.port, 8765)
        self.assertEqual(cfg.roots, [self.dir / "state/fleetglint/sources"])
        self.assertEqual(cfg.db_path, self.dir / "state/fleetglint/fleetglint.sqlite")
        self.assertEqual(cfg.viewer_roles, ["owner"])
        self.assertEqual(cfg.needs_you_hours, 24)
        self.assertEqual(cfg.inbox_old_after_s, 7200)

    def test_ui_values_are_read(self):
        cfg = config.load(self.write('[ui]\nviewer_roles = ["owner", "lead"]\n'
                                     'needs_you_hours = 6\ninbox_old_after_s = 60\n'))
        self.assertEqual(cfg.viewer_roles, ["owner", "lead"])
        self.assertEqual(cfg.needs_you_hours, 6)
        self.assertEqual(cfg.inbox_old_after_s, 60)

    def test_rejects_non_string_viewer_roles(self):
        with self.assertRaises(config.ConfigError):
            config.load(self.write('[ui]\nviewer_roles = [1]\n'))

    def test_values_are_read(self):
        cfg = config.load(self.write('[server]\nport = 9000\n[ingest]\nroots = ["/tmp/a"]\npoll_s = 1\n'
                                     '[adapters.tachiko_harness]\nenabled = false\n'))
        self.assertEqual(cfg.port, 9000)
        self.assertEqual(cfg.roots, [Path("/tmp/a")])
        self.assertEqual(cfg.poll_s, 1.0)
        self.assertEqual(cfg.harness.enabled, "false")

    def test_adapter_dirs_follow_tool_env(self):
        with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": "/x/claude", "CODEX_HOME": "/x/codex"}):
            cfg = config.load()
        self.assertEqual(cfg.claude_code.dir, Path("/x/claude/projects"))
        self.assertEqual(cfg.codex.dir, Path("/x/codex"))

    def test_rejects_non_loopback_host(self):
        with self.assertRaises(config.ConfigError):
            config.load(self.write('[server]\nhost = "0.0.0.0"\n'))

    def test_rejects_wrong_type(self):
        with self.assertRaises(config.ConfigError):
            config.load(self.write('[server]\nport = "80"\n'))

    def test_abandon_not_shorter_than_retention(self):
        with self.assertRaises(config.ConfigError):
            config.load(self.write('[retention]\nsegment_days = 30\nabandon_days = 10\n'))


if __name__ == "__main__":
    unittest.main()
