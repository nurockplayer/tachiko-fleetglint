"""Check examples/v1 against schema/v1/record.schema.json (dev only; needs jsonschema)."""
import json
import pathlib
import sys

import jsonschema

ROOT = pathlib.Path(__file__).resolve().parent.parent
schema = json.loads((ROOT / "schema/v1/record.schema.json").read_text())
jsonschema.Draft202012Validator.check_schema(schema)
validator = jsonschema.Draft202012Validator(schema)
failures = 0

for path in sorted((ROOT / "examples/v1/valid").glob("*.ndjson")):
    for n, line in enumerate(path.read_text().splitlines(), 1):
        errors = list(validator.iter_errors(json.loads(line)))
        if errors:
            failures += 1
            print(f"FAIL {path.name}:{n} should be valid: {errors[0].message}")

for path in sorted((ROOT / "examples/v1/invalid").glob("*.json")):
    if validator.is_valid(json.loads(path.read_text())):
        failures += 1
        print(f"FAIL {path.name} should be invalid")

print("ok" if not failures else f"{failures} failure(s)")
sys.exit(1 if failures else 0)
