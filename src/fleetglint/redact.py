"""Redact secrets from text before it is shown or copied (docs/spec.md §9).

Ported from tachiko-harness share/redact.py (same author): credential-named environment
values, token shapes and whole PEM private-key blocks become "[redacted]".
"""
import hmac
import os
import re
from functools import lru_cache
from threading import Lock

REPLACEMENT = "[redacted]"
NAME = re.compile(r"TOKEN|SECRET|PASSWORD|PASSWD|API_KEY|_KEY$|CREDENTIAL|AUTH", re.I)
BEGIN_KEY = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")
END_KEY = re.compile(r"-----END [A-Z ]*PRIVATE KEY-----")
SHAPES = (
    (re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}"), REPLACEMENT),
    (re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"), REPLACEMENT),
    (re.compile(r"github_pat_[A-Za-z0-9_]{20,}"), REPLACEMENT),
    (re.compile(r"sk-[A-Za-z0-9_-]{20,}"), REPLACEMENT),
    (re.compile(r"AIza[0-9A-Za-z_-]{35}"), REPLACEMENT),
    (re.compile(r"npm_[A-Za-z0-9]{36}"), REPLACEMENT),
    (re.compile(r"AKIA[0-9A-Z]{16}"), REPLACEMENT),
    (re.compile(r"xox[abprs]-[A-Za-z0-9-]{10,}"), REPLACEMENT),
    (re.compile(r"glpat-[A-Za-z0-9_-]{20,}"), REPLACEMENT),
    (re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"), REPLACEMENT),
    (re.compile(r"(?i)(authorization:\s*bearer\s+)\S+"), r"\1" + REPLACEMENT),
    (re.compile(r"(?i)(authorization:\s*basic\s+)\S+"), r"\1" + REPLACEMENT),
)


def redact(text, env=None):
    """Return (redacted text, number of secret occurrences replaced)."""
    return with_credentials(text, credential_values(env))


def with_credentials(text, values):
    text, count = _redact_pem(text)
    for value in values:
        text, replaced = re.subn(re.escape(value), REPLACEMENT, text)
        count += replaced
    for pattern, replacement in SHAPES:
        text, replaced = pattern.subn(replacement, text)
        count += replaced
    return text, count


def credential_values(env=None):
    env = os.environ if env is None else env
    found = (value for name, value in env.items() if len(value) >= 8 and NAME.search(name))
    return tuple(sorted(found, key=len, reverse=True))


@lru_cache(maxsize=4096)
def contains_secret(text, values):
    return with_credentials(text, values)[1] > 0


class OpaqueTokens:
    """Process-local aliases for secret-bearing names and lookup IDs."""

    def __init__(self):
        self._key = os.urandom(32)
        self._tokens = {}
        self._originals = {}
        self._lock = Lock()

    def encode(self, original, reserved=()):
        with self._lock:
            token = self._tokens.get(original)
            if token is not None and token not in reserved:
                return token
            digest = hmac.digest(self._key, original.encode("utf-8", "surrogatepass"), "sha256").hex()
            for length in range(12, len(digest) + 1):
                token = f"[redacted:{digest[:length]}]"
                if token not in reserved and self._originals.get(token, original) == original:
                    self._originals[token] = original
                    self._tokens.setdefault(original, token)
                    return token
        raise RuntimeError("exhausted opaque redaction token")

    def resolve(self, value):
        return self._originals.get(value, value)


def _redact_pem(text):
    """Collapse each private-key block to one replacement, including an unterminated block."""
    lines = text.splitlines(keepends=True)
    first_begin = next((i for i, line in enumerate(lines) if BEGIN_KEY.search(line)), len(lines))
    in_key = any(END_KEY.search(line) for line in lines[:first_begin])
    out = [REPLACEMENT] if in_key else []
    count = 1 if in_key else 0
    for line in lines:
        if in_key:
            if END_KEY.search(line):
                out.append(_line_ending(line))
                in_key = False
            continue
        if BEGIN_KEY.search(line):
            out.append(REPLACEMENT)
            count += 1
            if END_KEY.search(line):
                out.append(_line_ending(line))
            else:
                in_key = True
            continue
        out.append(line)
    return "".join(out), count


def _line_ending(line):
    return line[len(line.rstrip("\r\n")):]
