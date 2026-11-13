"""Resolve a working directory to its project name."""
import os
import re
from pathlib import Path


def _clip(value, limit):
    return value[:limit] if len(value) > limit else value


def _git_repo_name(path):
    """The repo a directory is in, from its `.git` entry; a worktree's `.git` file names the repo."""
    current = Path(path)
    for directory in [current, *current.parents][:8]:
        if not directory.exists() and re.fullmatch(r"(.+)-wt(?:-.+)?", directory.name):
            return None
        entry = directory / ".git"
        try:
            if entry.is_dir():
                return directory.name
            if entry.is_file():
                with entry.open(encoding="utf-8", errors="replace") as handle:
                    line = handle.read(4096).strip()
                if line.startswith("gitdir:") and "/worktrees/" in line:
                    common = line[len("gitdir:"):].strip().rsplit("/worktrees/", 1)[0]
                    if common.endswith("/.git"):
                        common = common[:-len("/.git")]
                    return os.path.basename(common.removesuffix(".git").rstrip("/"))
                return directory.name
        except OSError:
            return None
    return None


def project_from_path(path):
    if not isinstance(path, str) or not path:
        return None
    path = path.split("/.claude/", 1)[0]
    name = _git_repo_name(path)
    if not name:
        for component in reversed(Path(path).parts):
            match = re.fullmatch(r"(.+)-wt(?:-.+)?", component)
            if match:
                name = match.group(1)
                break
    return _clip(name or os.path.basename(path.rstrip("/")), 200) or None
