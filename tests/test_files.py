import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fleetglint import files


def fake_redact(text):
    return text.replace("SECRET", "[REDACTED]"), text.count("SECRET")


class ReadTailTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / "root"
        self.root.mkdir()
        self.roots = [self.root]

    def write(self, name, data, root=None):
        path = (root or self.root) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def read(self, path, max_bytes=1024, redact=fake_redact):
        return files.read_tail(path, self.roots, max_bytes, redact)

    def test_reads_a_file_inside_the_root(self):
        path = self.write("a.log", b"hello\n")
        self.assertEqual(self.read(path), {"readable": True, "path": os.path.realpath(path),
                                           "size": 6, "truncated": False,
                                           "text": "hello\n", "redactions": 0})

    def test_symlink_escaping_the_root_is_refused(self):
        outside = self.base / "outside"
        outside.mkdir()
        secret = self.write("secret.txt", b"secret", root=outside)
        link = self.root / "link"
        link.symlink_to(secret)
        self.assertEqual(self.read(link), {"readable": False, "reason": "outside_allowed_roots"})

    def test_symlink_inside_the_root_is_followed(self):
        real = self.write("real.txt", b"fine")
        link = self.root / "alias"
        link.symlink_to(real)
        self.assertEqual(self.read(link)["text"], "fine")

    def test_dotdot_does_not_escape_the_root(self):
        outside = self.base / "outside"
        outside.mkdir()
        secret = self.write("secret.txt", b"secret", root=outside)
        path = self.root / ".." / "outside" / secret.name
        self.assertEqual(self.read(path), {"readable": False, "reason": "outside_allowed_roots"})

    def test_intermediate_symlink_swap_is_caught(self):
        outside = self.base / "outside"
        outside.mkdir()
        (outside / "key").write_bytes(b"secret")
        job = self.root / "job"
        job.mkdir()
        (job / "key").write_bytes(b"inside")

        real_open = os.open
        swapped = []

        def swapping_open(target, flags, *args, **kwargs):
            if not swapped:  # runs between realpath and open
                swapped.append(True)
                job.rename(self.base / "job-old")
                job.symlink_to(outside)
            return real_open(target, flags, *args, **kwargs)

        with mock.patch.object(files.os, "open", side_effect=swapping_open):
            result = self.read(job / "key")
        self.assertEqual(result, {"readable": False, "reason": "outside_allowed_roots"})

    def test_prefix_sibling_directory_is_outside(self):
        sibling = self.base / "root2"
        path = self.write("f.txt", b"x", root=sibling)
        self.assertEqual(self.read(path), {"readable": False, "reason": "outside_allowed_roots"})

    def test_fifo_is_not_regular_and_does_not_block(self):
        path = self.root / "pipe"
        os.mkfifo(path)
        self.assertEqual(self.read(path), {"readable": False, "reason": "not_regular_file"})

    def test_directory_is_not_regular(self):
        path = self.root / "dir"
        path.mkdir()
        self.assertEqual(self.read(path), {"readable": False, "reason": "not_regular_file"})

    def test_missing_file(self):
        self.assertEqual(self.read(self.root / "nope.log"),
                         {"readable": False, "reason": "missing"})

    def test_no_path(self):
        for value in (None, "", 5):
            with self.subTest(value=value):
                self.assertEqual(self.read(value), {"readable": False, "reason": "no_path"})

    def test_relative_path_is_outside(self):
        self.write("a.log", b"x")
        old = os.getcwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, old)
        self.assertEqual(self.read("a.log"),
                         {"readable": False, "reason": "outside_allowed_roots"})

    def test_no_allowed_roots(self):
        path = self.write("a.log", b"x")
        self.assertEqual(files.read_tail(path, [], 1024, fake_redact),
                         {"readable": False, "reason": "outside_allowed_roots"})

    def test_only_the_tail_is_read(self):
        content = b"head" + b"x" * 100_000
        path = self.write("big.log", content)
        result = self.read(path, max_bytes=1000)
        self.assertTrue(result["truncated"])
        self.assertEqual(result["size"], len(content))
        self.assertEqual(result["text"], content[-1000:].decode())

    def test_partial_utf8_at_the_cut_is_dropped(self):
        path = self.write("utf8.log", "é".encode() * 10)
        result = self.read(path, max_bytes=5)  # cut lands on a continuation byte
        self.assertTrue(result["truncated"])
        self.assertEqual(result["text"], "éé")

    def test_invalid_utf8_is_refused(self):
        path = self.write("bin.log", b"\xff" * 100)
        self.assertEqual(self.read(path), {"readable": False, "reason": "not_utf8"})

    def test_sparse_invalid_utf8_is_replaced(self):
        path = self.write("mixed.log", b"clean text " * 100 + b"\xff")
        result = self.read(path)
        self.assertTrue(result["readable"])
        self.assertTrue(result["text"].endswith("�"))

    def test_redaction_count_is_passed_through(self):
        path = self.write("env.log", b"token SECRET here")
        result = self.read(path)
        self.assertEqual(result["redactions"], 1)
        self.assertEqual(result["text"], "token [REDACTED] here")

    def test_plain_string_redactor_counts_markers(self):
        path = self.write("env.log", b"SECRET and SECRET")
        result = self.read(path, redact=lambda text: text.replace("SECRET", "[REDACTED]"))
        self.assertEqual(result["redactions"], 2)

    def test_non_readable_result_has_no_content(self):
        result = self.read(self.root / "nope.log")
        self.assertEqual(set(result), {"readable", "reason"})


class IsReadableTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / "root"
        self.root.mkdir()
        self.roots = [self.root]

    def test_true_for_a_regular_file_inside(self):
        path = self.root / "a.log"
        path.write_bytes(b"x")
        self.assertTrue(files.is_readable(path, self.roots))

    def test_false_for_everything_else(self):
        outside = self.base / "outside"
        outside.mkdir()
        secret = outside / "s.txt"
        secret.write_bytes(b"x")
        link = self.root / "link"
        link.symlink_to(secret)
        fifo = self.root / "pipe"
        os.mkfifo(fifo)
        directory = self.root / "dir"
        directory.mkdir()
        for value in (None, link, fifo, directory, self.root / "nope.log"):
            with self.subTest(value=value):
                self.assertFalse(files.is_readable(value, self.roots))


if __name__ == "__main__":
    unittest.main()
