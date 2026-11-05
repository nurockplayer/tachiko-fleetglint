"""Safe bounded tail reads of files a record points at (spec §9)."""
import os
import re
import stat
import sys
from pathlib import Path

_NOT_UTF8_RATIO = 0.10
_REDACTED_MARKER = re.compile(r"\[redacted[^\]]*\]", re.IGNORECASE)


def _resolved_roots(allowed_roots):
    return [Path(os.path.realpath(str(root))) for root in allowed_roots]


def _inside(path, roots):
    return any(path.is_relative_to(root) for root in roots)


def _opened_path(fd):
    """The path the open fd names, or None when the OS cannot report it.

    Re-checking containment on this closes the window in which an intermediate
    directory can be swapped for a symlink between realpath and open.
    """
    if sys.platform.startswith("linux"):
        try:
            return os.readlink(f"/proc/self/fd/{fd}")
        except OSError:
            return None
    if sys.platform == "darwin":
        import fcntl
        try:
            value = fcntl.fcntl(fd, fcntl.F_GETPATH, b"\0" * 1024)
        except (OSError, ValueError):
            return None
        return os.fsdecode(value.split(b"\0", 1)[0])
    return None


def _open_regular(path, allowed_roots):
    """(fd, size) for an allowed regular file, else (None, reason)."""
    try:
        path = os.fspath(path) if path else None
    except TypeError:
        path = None
    if not path:
        return None, "no_path"
    if not os.path.isabs(path):
        return None, "outside_allowed_roots"
    roots = _resolved_roots(allowed_roots)
    resolved = Path(os.path.realpath(path))
    if not _inside(resolved, roots):
        return None, "outside_allowed_roots"
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(resolved, flags)
    except (OSError, ValueError):
        # Missing, unreadable, a symlink race or a bad path: none of these may leak
        # a reason the API does not know, so they all read as "missing".
        return None, "missing"
    try:
        info = os.fstat(fd)
    except OSError:
        os.close(fd)
        return None, "missing"
    if not stat.S_ISREG(info.st_mode):
        os.close(fd)
        return None, "not_regular_file"
    actual = _opened_path(fd)
    if actual is None or not _inside(Path(actual), roots):
        os.close(fd)
        return None, "outside_allowed_roots"
    return fd, info.st_size


def _read_tail(fd, size, max_bytes):
    limit = max(0, max_bytes)
    offset = max(0, size - limit)
    os.lseek(fd, offset, os.SEEK_SET)
    chunks = []
    remaining = limit
    while remaining > 0:
        chunk = os.read(fd, remaining)
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    data = b"".join(chunks)
    if offset:
        # The cut may land inside a UTF-8 sequence: drop its leading continuation bytes.
        while data and 0x80 <= data[0] <= 0xBF:
            data = data[1:]
    return data, offset


def _apply_redact(func, text):
    """Redacted text and the number of substitutions.

    `fleetglint.redact.redact` may return the text alone or a (text, count) pair.
    """
    result = func(text)
    if isinstance(result, tuple):
        return result[0], int(result[1])
    return result, len(_REDACTED_MARKER.findall(result))


def is_readable(path, allowed_roots) -> bool:
    """Would `read_tail` open this path (spec §9)? Checks without reading the file."""
    fd, _ = _open_regular(path, allowed_roots)
    if fd is None:
        return False
    os.close(fd)
    return True


def read_tail(path: str | None, allowed_roots: list[Path], max_bytes: int, redact=None) -> dict:
    """Read at most the last `max_bytes` of a file inside an allowed root (spec §9)."""
    fd, info = _open_regular(path, allowed_roots)
    if fd is None:
        return {"readable": False, "reason": info}
    try:
        data, offset = _read_tail(fd, info, max_bytes)
    except OSError:
        return {"readable": False, "reason": "missing"}
    finally:
        os.close(fd)
    text = data.decode("utf-8", errors="replace")
    if text and text.count("\ufffd") / len(text) > _NOT_UTF8_RATIO:
        return {"readable": False, "reason": "not_utf8"}
    if redact is None:
        from fleetglint.redact import redact as redact_text
        redact = redact_text
    text, redactions = _apply_redact(redact, text)
    return {
        "readable": True,
        "path": os.path.realpath(path),
        "size": info,
        "truncated": offset > 0,
        "text": text,
        "redactions": redactions,
    }
