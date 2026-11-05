"""Render packaging/homebrew/fleetglint.rb.in with a version and sdist sha256."""
import hashlib
import pathlib
import sys

TEMPLATE = pathlib.Path(__file__).resolve().parent.parent / "packaging/homebrew/fleetglint.rb.in"


def render(version, sdist):
    digest = hashlib.sha256(pathlib.Path(sdist).read_bytes()).hexdigest()
    text = TEMPLATE.read_text()
    return text.replace("@VERSION@", version).replace("@SHA256@", digest)


def main(argv):
    if len(argv) != 3:
        print("usage: render_formula.py VERSION SDIST_PATH", file=sys.stderr)
        return 2
    sys.stdout.write(render(argv[1], argv[2]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
