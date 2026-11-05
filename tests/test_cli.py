import contextlib
import io
import pathlib
import unittest

from fleetglint import __version__, cli

ROOT = pathlib.Path(__file__).resolve().parent.parent


class CliTest(unittest.TestCase):
    def test_version(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(cli.main(["version"]), 0)
        self.assertIn(__version__, out.getvalue())

    def test_no_command_is_usage_error(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main([]), 2)

    def test_packaged_schema_matches_repo_schema(self):
        packaged = ROOT / "src/fleetglint/data/record.schema.json"
        self.assertEqual(packaged.read_bytes(), (ROOT / "schema/v1/record.schema.json").read_bytes())


if __name__ == "__main__":
    unittest.main()
