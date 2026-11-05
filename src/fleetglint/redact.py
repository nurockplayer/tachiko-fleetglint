"""Redact secrets from text before it is shown or copied (docs/spec.md §9).

Ported from tachiko-harness share/redact.py (same author): credential-named environment
values, token shapes and whole PEM private-key blocks become "[redacted]".
"""
import os
import re

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
)


def redact(text, env=None):
    """Return (redacted text, number of secret occurrences replaced)."""
    env = os.environ if env is None else env
    text, count = _redact_pem(text)
    for value, _name in _env_secrets(env):
        text, replaced = re.subn(re.escape(value), REPLACEMENT, text)
        count += replaced
    for pattern, replacement in SHAPES:
        text, replaced = pattern.subn(replacement, text)
        count += replaced
    return text, count


def _env_secrets(env):
    found = [(value, name) for name, value in env.items() if len(value) >= 8 and NAME.search(name)]
    return sorted(found, key=lambda item: len(item[0]), reverse=True)


def _redact_pem(text):
    """Collapse each private-key block to one replacement, including an unterminated block."""
    lines = text.splitlines()
    first_begin = next((i for i, line in enumerate(lines) if BEGIN_KEY.search(line)), len(lines))
    in_key = any(END_KEY.search(line) for line in lines[:first_begin])
    out = [REPLACEMENT] if in_key else []
    count = 1 if in_key else 0
    for line in lines:
        if in_key:
            if END_KEY.search(line):
                in_key = False
            continue
        if BEGIN_KEY.search(line):
            out.append(REPLACEMENT)
            count += 1
            if not END_KEY.search(line):
                in_key = True
            continue
        out.append(line)
    return "\n".join(out), count
