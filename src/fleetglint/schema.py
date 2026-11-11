"""A small JSON Schema 2020-12 interpreter for the v1 record schema (docs/spec.md §2, §7.3)."""
import importlib.resources
import json
import math
import re
import sys
from datetime import datetime

MAX_LINE_BYTES = 65536
RECORD_TYPES = frozenset({"run", "job", "inbox_item", "session", "decision"})

_ANNOTATIONS = {"title", "description", "$schema", "$id"}
_KEYWORDS = _ANNOTATIONS | {
    "$defs", "$ref", "type", "enum", "const", "required", "properties", "items",
    "maxItems", "minLength", "maxLength", "minimum", "pattern", "format",
    "allOf", "anyOf", "oneOf", "not", "if", "then",
}
_DATETIME = re.compile(r"\A\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})\Z")
_REF_PREFIX = "#/$defs/"


def _load():
    path = importlib.resources.files("fleetglint").joinpath("data").joinpath("record.schema.json")
    document = json.loads(path.read_text(encoding="utf-8"))
    _check(document, document)
    return document


def _check(schema, root):
    """Reject schema keywords and references this interpreter would silently ignore."""
    if isinstance(schema, bool):
        return
    if not isinstance(schema, dict):
        raise ValueError(f"schema is not an object: {schema!r}")
    for keyword, value in schema.items():
        if keyword not in _KEYWORDS:
            raise ValueError(f"unsupported schema keyword {keyword!r}")
        if keyword == "$ref":
            if not value.startswith(_REF_PREFIX) or value[len(_REF_PREFIX):] not in root.get("$defs", {}):
                raise ValueError(f"unsupported $ref {value!r}")
        elif keyword in ("properties", "$defs"):
            for sub in value.values():
                _check(sub, root)
        elif keyword in ("items", "not", "if", "then"):
            _check(value, root)
        elif keyword in ("allOf", "anyOf", "oneOf"):
            for sub in value:
                _check(sub, root)


SCHEMA = _load()


def validate(obj):
    """Return every schema violation for one record; an empty list means valid."""
    return _errors(obj, SCHEMA, "")


def classify_line(raw, expected_source_id=None, max_bytes=MAX_LINE_BYTES):
    """Classify one NDJSON line: (record, None, None) or (None, reason, detail) per spec §7.3."""
    if len(raw) > max_bytes:
        return None, "too_large", f"{len(raw)} bytes"
    try:
        record = json.loads(raw.decode("utf-8"), parse_constant=_reject_constant)
    except ValueError as exc:
        return None, "invalid_json", str(exc)
    if not isinstance(record, dict):
        return None, "invalid_json", f"not a JSON object: {_json_type(record)}"
    version = record.get("v")
    if isinstance(version, bool) or not isinstance(version, int) or version != 1:
        return None, "unsupported_version", f"v={version!r}"
    record_type = record.get("type")
    if not isinstance(record_type, str) or record_type not in RECORD_TYPES:
        return None, "unsupported_type", f"type={record_type!r}"
    errors = validate(record)
    if errors:
        return None, "schema", "; ".join(errors)
    if expected_source_id is not None and record.get("source_id") != expected_source_id:
        return None, "source_mismatch", f"{record.get('source_id')!r} != {expected_source_id!r}"
    return record, None, None


def _reject_constant(value):
    raise ValueError(f"non-standard JSON constant {value}")


def run(args):
    """`fleetglint check [FILE…]`: report bad lines and a summary; exit 1 when any line is bad."""
    names = args.files or ["<stdin>"]
    total = bad = 0
    for name in names:
        if args.files:
            try:
                stream = open(name, "rb")
            except OSError as exc:
                print(f"{name}: {exc}", file=sys.stderr)
                return 3
            source = stream
        else:
            source = sys.stdin.buffer
        try:
            for number, raw in enumerate(source, 1):
                total += 1
                if not raw.endswith(b"\n"):
                    bad += 1
                    print(f"{name}:{number}: incomplete_line: "
                          f"the reader would wait for the newline")
                    continue
                _, reason, detail = classify_line(raw)
                if reason:
                    bad += 1
                    print(f"{name}:{number}: {reason}: {detail}")
        finally:
            if args.files:
                source.close()
    print(f"{total} line(s), {bad} invalid")
    return 1 if bad else 0


def _errors(value, schema, path):
    if schema is True:
        return []
    if schema is False:
        return [f"{_display(path)}: not allowed"]
    errors = []
    if "$ref" in schema:
        errors += _errors(value, SCHEMA["$defs"][schema["$ref"][len(_REF_PREFIX):]], path)
    if "type" in schema:
        types = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_has_type(value, name) for name in types):
            errors.append(f"{_display(path)}: expected {' or '.join(types)}, got {_json_type(value)}")
    if "const" in schema and not _equal(value, schema["const"]):
        errors.append(f"{_display(path)}: expected {schema['const']!r}")
    if "enum" in schema and not any(_equal(value, option) for option in schema["enum"]):
        errors.append(f"{_display(path)}: not one of {schema['enum']!r}")
    for sub in schema.get("allOf", []):
        errors += _errors(value, sub, path)
    if "anyOf" in schema and not any(not _errors(value, sub, path) for sub in schema["anyOf"]):
        errors.append(f"{_display(path)}: does not match any allowed form")
    if "oneOf" in schema:
        matched = sum(1 for sub in schema["oneOf"] if not _errors(value, sub, path))
        if matched != 1:
            errors.append(f"{_display(path)}: matches {matched} of the required alternatives, expected 1")
    if "not" in schema and not _errors(value, schema["not"], path):
        errors.append(f"{_display(path)}: must not match the excluded form")
    if "if" in schema and not _errors(value, schema["if"], path) and "then" in schema:
        errors += _errors(value, schema["then"], path)
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{_display(path)}: missing required property {key!r}")
        for key, sub in schema.get("properties", {}).items():
            if key in value:
                errors += _errors(value[key], sub, f"{path}/{key}")
    if isinstance(value, list):
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errors.append(f"{_display(path)}: more than {schema['maxItems']} items")
        if "items" in schema:
            for index, item in enumerate(value):
                errors += _errors(item, schema["items"], f"{path}/{index}")
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errors.append(f"{_display(path)}: shorter than {schema['minLength']} characters")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errors.append(f"{_display(path)}: longer than {schema['maxLength']} characters")
        if "pattern" in schema and not _matches(schema["pattern"], value):
            errors.append(f"{_display(path)}: does not match {schema['pattern']!r}")
        if schema.get("format") == "date-time" and not _is_datetime(value):
            errors.append(f"{_display(path)}: not an RFC 3339 date-time with offset")
    if _is_number(value) and "minimum" in schema and value < schema["minimum"]:
        errors.append(f"{_display(path)}: less than {schema['minimum']}")
    return errors


def _display(path):
    return path or "/"


def _is_number(value):
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    return isinstance(value, float) and math.isfinite(value)


def _has_type(value, name):
    if name == "object":
        return isinstance(value, dict)
    if name == "array":
        return isinstance(value, list)
    if name == "string":
        return isinstance(value, str)
    if name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if name == "number":
        return _is_number(value)
    if name == "boolean":
        return isinstance(value, bool)
    if name == "null":
        return value is None
    raise ValueError(f"unsupported type {name!r}")


def _json_type(value):
    if isinstance(value, bool):
        return "boolean"
    if value is None:
        return "null"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _equal(left, right):
    """JSON equality: booleans equal only booleans, numbers compare numerically."""
    if isinstance(left, bool) or isinstance(right, bool):
        return isinstance(left, bool) and isinstance(right, bool) and left == right
    if _is_number(left) and _is_number(right):
        return left == right
    if type(left) is not type(right):
        return False
    if isinstance(left, list):
        return len(left) == len(right) and all(_equal(a, b) for a, b in zip(left, right))
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(_equal(left[key], right[key]) for key in left)
    return left == right


def _matches(pattern, value):
    # Python's $ also matches just before a trailing newline; ECMA-262's does not, so a
    # fully anchored schema pattern is matched against the whole string.
    if pattern.startswith("^") and pattern.endswith("$"):
        return re.fullmatch(pattern, value) is not None
    return re.search(pattern, value) is not None


def _is_datetime(value):
    if not _DATETIME.match(value):
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True
