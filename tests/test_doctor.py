import argparse
import contextlib
import io
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from fleetglint import config, doctor, store

FIXTURES = Path(__file__).parent / "fixtures"
JST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 6, 12, 0, tzinfo=JST)


class DoctorTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.roots = self.dir / "sources"
        self.db = self.dir / "fleetglint.sqlite"
        self.harness = self.dir / "harness"
        self.claude = self.dir / "claude" / "projects"
        self.codex = self.dir / "codex"
        patcher = mock.patch.dict(os.environ, {"XDG_STATE_HOME": str(self.dir / "state"),
                                               "XDG_CONFIG_HOME": str(self.dir / "config")})
        patcher.start()
        self.addCleanup(patcher.stop)

    def config_file(self):
        path = self.dir / "config.toml"
        path.write_text(
            "[server]\nport = 1\n\n"
            "[ingest]\n"
            f'roots = ["{self.roots}"]\n'
            f'db_path = "{self.db}"\n\n'
            "[adapters.tachiko_harness]\n"
            f'state_dir = "{self.harness}"\n\n'
            "[adapters.claude_code]\n"
            f'dir = "{self.claude}"\n\n'
            "[adapters.codex]\n"
            f'dir = "{self.codex}"\n')
        return path

    def run_doctor(self):
        args = argparse.Namespace(config=str(self.config_file()))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = doctor.run(args, now=NOW)
        return code, out.getvalue()

    def test_no_data_explains_and_exits_zero(self):
        code, text = self.run_doctor()
        self.assertEqual(code, 0)
        self.assertIn("no problems found", text)
        self.assertIn("not created yet: run fleetglint serve", text)
        self.assertIn("missing; created on first write", text)
        self.assertIn("not present", text)
        self.assertIn("not running on http://127.0.0.1:1 (informational)", text)
        self.assertIn("privacy: adapters read", text)

    def test_discontinuity_source_is_a_problem(self):
        conn = store.open_db(self.db)
        store.ensure_source(conn, "demo@fleetglint", "ndjson", str(self.roots))
        store.update_source(conn, "demo@fleetglint", status="discontinuity", detail="segment gap")
        conn.close()

        code, text = self.run_doctor()
        self.assertEqual(code, 1)
        self.assertIn("discontinuity", text)
        self.assertIn("fix: fleetglint source reset demo@fleetglint", text)

    def test_adapters_report_scan_counts(self):
        shutil.copytree(FIXTURES / "harness" / "state", self.harness)
        shutil.copytree(FIXTURES / "claude_code" / "projects", self.claude)
        shutil.copytree(FIXTURES / "codex", self.codex)

        code, text = self.run_doctor()
        self.assertEqual(code, 0)
        self.assertIn("adapter tachiko-harness (enabled: auto)", text)
        self.assertIn("adapter claude-code (enabled: auto)", text)
        self.assertIn("adapter codex-cli (enabled: auto)", text)
        self.assertRegex(text, r"scan: \d+ record\(s\) in \d+ ms")
        self.assertRegex(text, r"run: \d+ \(")
        self.assertRegex(text, r"session: 3 \(")


if __name__ == "__main__":
    unittest.main()
