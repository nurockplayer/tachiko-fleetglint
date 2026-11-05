"""Check dist/ archives contain the built UI and schema, and no dev-only trees."""
import pathlib
import sys
import tarfile
import zipfile

REQUIRED = ("fleetglint/web/index.html", "fleetglint/data/record.schema.json")
FORBIDDEN = {"ui", "tests", ".claude"}


def wheel_members(path):
    with zipfile.ZipFile(path) as zf:
        return [name for name in zf.namelist() if not name.endswith("/")]


def sdist_members(path):
    with tarfile.open(path) as tar:
        names = [member.name for member in tar.getmembers() if member.isfile()]
    # An sdist wraps everything in one directory named after the project, and a
    # src layout keeps the package under src/.
    tops = {name.split("/", 1)[0] for name in names}
    if len(tops) == 1:
        top = tops.pop() + "/"
        names = [name[len(top):] for name in names if name.startswith(top)]
    return [name[len("src/"):] if name.startswith("src/") else name for name in names]


def problems(names):
    found = []
    for required in REQUIRED:
        if required not in names:
            found.append(f"missing {required}")
    if not any(name.startswith("fleetglint/web/assets/") and name.endswith(".js")
               for name in names):
        found.append("missing fleetglint/web/assets/*.js")
    for name in names:
        if name.split("/", 1)[0] in FORBIDDEN:
            found.append(f"unexpected {name}")
    return found


def main(argv):
    if len(argv) != 2:
        print("usage: check_dist.py DIST_DIR", file=sys.stderr)
        return 2
    dist = pathlib.Path(argv[1])
    archives = [
        (path, wheel_members) for path in sorted(dist.glob("*.whl"))
    ] + [
        (path, sdist_members) for path in sorted(dist.glob("*.tar.gz"))
    ]
    if not archives:
        print(f"FAIL no wheel or sdist in {dist}", file=sys.stderr)
        return 1

    failed = False
    for path, members in archives:
        found = problems(members(path))
        if found:
            failed = True
            for problem in found:
                print(f"FAIL {path.name}: {problem}")
        else:
            print(f"{path.name}: ok ({len(members(path))} files)")
    print("ok" if not failed else "failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
