import contextlib
import io
import json
import multiprocessing
import os
import pathlib
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from fleetglint import emit


def make_record(**overrides):
    record = {"v": 1, "type": "run", "id": "r1", "source_id": "demo",
              "updated_at": "2026-11-05T09:00:00Z", "state": "queued", "agent": "aider"}
    record.update(overrides)
    return record


def append_many(root, prefix, count):
    for index in range(count):
        emit.append_record(make_record(id=f"{prefix}-{index}"), pathlib.Path(root))


def run_emit(payload, root, source_id=None, config=None):
    args = SimpleNamespace(source_id=source_id, root=str(root), config=config)
    with mock.patch("sys.stdin", io.TextIOWrapper(io.BytesIO(payload))):
        with contextlib.redirect_stderr(io.StringIO()):
            return emit.run(args)


class AppendRecordTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        self.dir = self.root / "demo"

    def test_one_line_per_call(self):
        first = emit.append_record(make_record(), self.root)
        second = emit.append_record(make_record(id="r2"), self.root)
        self.assertEqual(first, second)
        self.assertEqual(first.name, "0000000001.ndjson")
        data = first.read_bytes()
        self.assertTrue(data.endswith(b"\n"))
        lines = data.decode().splitlines()
        self.assertEqual([json.loads(line)["id"] for line in lines], ["r1", "r2"])
        self.assertEqual(lines[0], json.dumps(make_record(), separators=(",", ":"), ensure_ascii=False))

    def test_rotation_at_the_size_limit(self):
        with mock.patch.object(emit, "SEGMENT_LIMIT", 1):
            first = emit.append_record(make_record(), self.root)
            second = emit.append_record(make_record(id="r2"), self.root)
        self.assertEqual(first.name, "0000000001.ndjson")
        self.assertEqual(second.name, "0000000002.ndjson")
        self.assertEqual(json.loads(first.read_text())["id"], "r1")
        self.assertEqual(json.loads(second.read_text())["id"], "r2")

    def test_starts_after_a_compressed_segment(self):
        self.dir.mkdir()
        (self.dir / "0000000001.ndjson.gz").write_bytes(b"")
        segment = emit.append_record(make_record(), self.root)
        self.assertEqual(segment.name, "0000000002.ndjson")

    def test_never_appends_below_a_compressed_higher_segment(self):
        self.dir.mkdir()
        (self.dir / "0000000001.ndjson").write_text("")
        (self.dir / "0000000002.ndjson.gz").write_bytes(b"")
        segment = emit.append_record(make_record(), self.root)
        self.assertEqual(segment.name, "0000000003.ndjson")
        self.assertEqual((self.dir / "0000000001.ndjson").read_text(), "")

    def test_final_line_over_the_limit_is_refused(self):
        with self.assertRaises(ValueError):
            emit.append_record(make_record(title="x" * 200, x_pad="y" * 70000), self.root)

    def test_never_truncates_an_existing_segment(self):
        self.dir.mkdir()
        existing = json.dumps(make_record(id="old"), separators=(",", ":")) + "\n"
        (self.dir / "0000000001.ndjson").write_text(existing)
        emit.append_record(make_record(id="new"), self.root)
        data = (self.dir / "0000000001.ndjson").read_text()
        self.assertTrue(data.startswith(existing))
        self.assertEqual(len(data.splitlines()), 2)

    def test_short_writes_are_completed(self):
        real_write = os.write

        def short_write(fd, data):
            return real_write(fd, bytes(data)[:7])

        with mock.patch.object(emit.os, "write", side_effect=short_write):
            emit.append_record(make_record(), self.root)
        line = (self.dir / "0000000001.ndjson").read_text()
        self.assertEqual(json.loads(line), make_record())

    def test_concurrent_appends_keep_every_line(self):
        method = "fork" if "fork" in multiprocessing.get_all_start_methods() else "spawn"
        context = multiprocessing.get_context(method)
        workers = [context.Process(target=append_many, args=(str(self.root), f"p{n}", 50))
                   for n in range(2)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(60)
            self.assertEqual(worker.exitcode, 0)
        lines = []
        for segment in sorted(self.dir.glob("*.ndjson")):
            lines += segment.read_text().splitlines()
        records = [json.loads(line) for line in lines]
        self.assertEqual(len(records), 100)
        self.assertEqual(len({record["id"] for record in records}), 100)


class EmitCommandTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)

    def test_valid_record_is_appended(self):
        self.assertEqual(run_emit(json.dumps(make_record()).encode(), self.root), 0)
        data = (self.root / "demo" / "0000000001.ndjson").read_text()
        self.assertEqual(json.loads(data)["id"], "r1")

    def test_source_id_option_fills_a_missing_field(self):
        record = make_record()
        del record["source_id"]
        self.assertEqual(run_emit(json.dumps(record).encode(), self.root, source_id="demo"), 0)
        data = (self.root / "demo" / "0000000001.ndjson").read_text()
        self.assertEqual(json.loads(data)["source_id"], "demo")

    def test_mismatched_source_id_is_refused(self):
        code = run_emit(json.dumps(make_record()).encode(), self.root, source_id="other")
        self.assertEqual(code, 1)
        self.assertFalse((self.root / "other").exists())

    def test_invalid_record_is_refused(self):
        record = make_record()
        del record["state"]
        self.assertEqual(run_emit(json.dumps(record).encode(), self.root), 1)
        self.assertFalse((self.root / "demo").exists())

    def test_oversized_record_is_refused(self):
        self.assertEqual(run_emit(b" " * 70000, self.root), 1)

    def test_bad_json_and_non_objects_are_refused(self):
        self.assertEqual(run_emit(b"{", self.root), 1)
        self.assertEqual(run_emit(b"[]", self.root), 1)

    def test_non_finite_unknown_field_is_refused(self):
        payload = (b'{"v":1,"type":"run","id":"r1","source_id":"demo",'
                   b'"updated_at":"2026-11-05T09:00:00Z","state":"queued","agent":"aider",'
                   b'"x_cost":NaN}')
        self.assertEqual(run_emit(payload, self.root), 1)
        self.assertFalse((self.root / "demo").exists())


if __name__ == "__main__":
    unittest.main()
