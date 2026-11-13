import contextlib
import io
import json
import pathlib
import tempfile
import unittest
from unittest import mock

from fleetglint import cli, schema

ROOT = pathlib.Path(__file__).resolve().parent.parent
VALID = ROOT / "examples/v1/valid"
INVALID = ROOT / "examples/v1/invalid"


def make_record(**overrides):
    record = {"v": 1, "type": "run", "id": "r1", "source_id": "demo",
              "updated_at": "2026-11-05T09:00:00Z", "state": "queued", "agent": "aider"}
    record.update(overrides)
    return record


class ExamplesTest(unittest.TestCase):
    def test_every_valid_example_line_is_valid(self):
        for path in sorted(VALID.glob("*.ndjson")):
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                with self.subTest(file=path.name, line=number):
                    self.assertEqual(schema.validate(json.loads(line)), [])

    def test_every_invalid_example_is_invalid(self):
        for path in sorted(INVALID.glob("*.json")):
            with self.subTest(file=path.name):
                record = json.loads(path.read_text(encoding="utf-8"))
                self.assertNotEqual(schema.validate(record), [])


class ValidateTest(unittest.TestCase):
    def test_decision_example(self):
        self.assertEqual(schema.validate(json.loads((VALID / "decision.json").read_text())), [])

    def test_error_path_and_enum_message(self):
        errors = schema.validate(make_record(state="bogus"))
        self.assertIn("/state: not one of", errors[0])

    def test_booleans_are_not_integers(self):
        self.assertTrue(schema.validate(make_record(stale_after_s=True)))
        self.assertTrue(schema.validate(make_record(
            state="running", started_at="2026-11-05T09:00:00Z",
            process={"host": "mbp", "pid": True})))

    def test_impossible_calendar_dates_and_hours(self):
        self.assertTrue(schema.validate(make_record(updated_at="2026-02-30T00:00:00Z")))
        self.assertTrue(schema.validate(make_record(updated_at="2026-11-05T25:00:00Z")))

    def test_trailing_newline_in_id_or_timestamp_fails(self):
        self.assertTrue(schema.validate(make_record(id="r1\n")))
        self.assertTrue(schema.validate(make_record(updated_at="2026-11-05T09:00:00Z\n")))

    def test_unknown_fields_pass(self):
        self.assertEqual(schema.validate(make_record(x_extra={"anything": [1, 2]})), [])

    def test_non_finite_numbers_are_not_numbers(self):
        cost = {"amount": float("nan"), "currency": "USD", "basis": "billed"}
        usage = {"basis": "measured", "cost": cost}
        self.assertTrue(schema.validate(make_record(usage=usage)))
        cost["amount"] = float("inf")
        self.assertTrue(schema.validate(make_record(usage=usage)))


class ClassifyLineTest(unittest.TestCase):
    def classify(self, obj, expected=None):
        return schema.classify_line(json.dumps(obj).encode() + b"\n", expected)

    def test_valid_line(self):
        record, reason, detail = self.classify(make_record())
        self.assertEqual((reason, detail), (None, None))
        self.assertEqual(record["id"], "r1")

    def test_invalid_json(self):
        for raw in (b"{not json\n", b"[]\n", b"\xff\n"):
            with self.subTest(raw=raw):
                self.assertEqual(schema.classify_line(raw, None)[1], "invalid_json")

    def test_too_large(self):
        raw = b"x" * (65 * 1024) + b"\n"
        record, reason, detail = schema.classify_line(raw, None)
        self.assertEqual((record, reason), (None, "too_large"))
        self.assertIn(str(len(raw)), detail)

    def test_unsupported_version(self):
        self.assertEqual(self.classify(make_record(v=2))[1], "unsupported_version")

    def test_unsupported_type(self):
        self.assertEqual(self.classify(make_record(type="review"))[1], "unsupported_type")

    def test_unhashable_type_and_version(self):
        self.assertEqual(self.classify(make_record(type=[]))[1], "unsupported_type")
        self.assertEqual(self.classify(make_record(type={}))[1], "unsupported_type")
        self.assertEqual(self.classify(make_record(v=[]))[1], "unsupported_version")
        self.assertEqual(self.classify(make_record(v={}))[1], "unsupported_version")

    def test_non_finite_constants_are_invalid_json(self):
        line = json.dumps(make_record())[:-1]
        for constant in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(constant=constant):
                raw = (line + f',"x":{constant}' + "}\n").encode()
                self.assertEqual(schema.classify_line(raw, None)[1], "invalid_json")

    def test_schema(self):
        bad = make_record()
        del bad["state"]
        self.assertEqual(self.classify(bad)[1], "schema")

    def test_source_mismatch(self):
        self.assertEqual(self.classify(make_record(source_id="demo"), "other")[1], "source_mismatch")
        self.assertIsNone(self.classify(make_record(source_id="demo"), "demo")[1])


class CheckCommandTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = pathlib.Path(self.tmp.name)

    def check(self, path):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli.main(["check", str(path)])
        return code, out.getvalue()

    def test_valid_file_exits_zero(self):
        path = self.dir / "good.ndjson"
        path.write_text(json.dumps(make_record()) + "\n")
        code, out = self.check(path)
        self.assertEqual(code, 0)
        self.assertIn("1 line(s), 0 invalid", out)

    def test_invalid_line_exits_one_with_position(self):
        path = self.dir / "bad.ndjson"
        path.write_text('{"v":1}\n' + json.dumps(make_record()) + "\n")
        code, out = self.check(path)
        self.assertEqual(code, 1)
        self.assertIn(f"{path}:1: unsupported_type: ", out)
        self.assertIn("2 line(s), 1 invalid", out)

    def test_final_line_without_newline_is_incomplete(self):
        path = self.dir / "partial.ndjson"
        path.write_bytes((json.dumps(make_record()) + "\n" + json.dumps(make_record(id="r2"))).encode())
        code, out = self.check(path)
        self.assertEqual(code, 1)
        self.assertIn(f"{path}:2: incomplete_line: the reader would wait for the newline", out)
        self.assertIn("2 line(s), 1 invalid", out)

    def test_stdin_when_no_files(self):
        out = io.StringIO()
        with mock.patch("sys.stdin", io.TextIOWrapper(io.BytesIO(b'{"v":1}\n'))):
            with contextlib.redirect_stdout(out):
                code = cli.main(["check"])
        self.assertEqual(code, 1)
        self.assertIn("<stdin>:1: unsupported_type: ", out.getvalue())


if __name__ == "__main__":
    unittest.main()
