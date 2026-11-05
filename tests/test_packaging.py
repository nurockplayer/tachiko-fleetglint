import hashlib
import io
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILES = {
    "fleetglint/__init__.py": "",
    "fleetglint/web/index.html": "<html></html>",
    "fleetglint/web/assets/index-abc123.js": "console.log(1);",
    "fleetglint/data/record.schema.json": "{}",
}


class PackagingTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def write_wheel(self, names):
        path = self.dir / "fleetglint-0.1.0.dev0-py3-none-any.whl"
        with zipfile.ZipFile(path, "w") as zf:
            for name in names:
                zf.writestr(name, FILES.get(name, ""))
        return path

    def write_sdist(self, names):
        path = self.dir / "fleetglint-0.1.0.dev0.tar.gz"
        with tarfile.open(path, "w:gz") as tar:
            for name in names:
                data = FILES.get(name, "").encode()
                info = tarfile.TarInfo(f"fleetglint-0.1.0.dev0/src/{name}")
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
        return path

    def check_dist(self):
        return subprocess.run([sys.executable, str(ROOT / "scripts/check_dist.py"), str(self.dir)],
                              capture_output=True, text=True)

    def test_check_dist_accepts_complete_archives(self):
        self.write_wheel(FILES)
        self.write_sdist(FILES)
        result = self.check_dist()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_check_dist_rejects_missing_web_index(self):
        names = [name for name in FILES if name != "fleetglint/web/index.html"]
        self.write_wheel(names)
        self.write_sdist(names)
        result = self.check_dist()
        self.assertEqual(result.returncode, 1)
        self.assertIn("fleetglint/web/index.html", result.stdout)

    def test_render_formula_fills_placeholders(self):
        sdist = self.dir / "fleetglint-0.1.0.dev0.tar.gz"
        sdist.write_bytes(b"sdist bytes")
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/render_formula.py"), "0.1.0.dev0", str(sdist)],
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("download/v0.1.0.dev0/fleetglint-0.1.0.dev0.tar.gz", result.stdout)
        self.assertIn(hashlib.sha256(b"sdist bytes").hexdigest(), result.stdout)
        self.assertNotIn("@VERSION@", result.stdout)
        self.assertNotIn("@SHA256@", result.stdout)
