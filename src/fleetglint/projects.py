"""Resolve a working directory to its project name."""
import os
import re
from pathlib import Path


def _clip(value, limit):
    return value[:limit] if len(value) > limit else value


def _git_repo_name(path):
    """The repo a directory is in, from its `.git` entry; a worktree's `.git` file names the repo."""
    current = Path(path)
    home = Path.home()
    for directory in [current, *current.parents][:8]:
        if len(directory.parts) <= 2 or directory == home or directory in home.parents:
            return None
        try:
            if not directory.exists() and re.fullmatch(r"(.+)-wt(?:-.+)?", directory.name):
                return None
            entry = directory / ".git"
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


def _review_repo_name(path):
    parts = Path(path).parts
    for index in range(len(parts) - 5):
        if parts[index:index + 3] == (".local", "state", "review"):
            return parts[index + 4]
    return None


def _is_boundary(path):
    current = Path(path)
    home = Path.home()
    if current == home or current in home.parents:
        return True
    parts = current.parts
    if parts == ("/",) or (parts[:2] == ("/", "Volumes") and len(parts) <= 3):
        return True
    for root in (Path("/tmp"), Path("/private/tmp"), Path("/var/tmp"), Path("/private/var/tmp")):
        if current == root:
            return True
        if root.parent.name != "var" and parts[:len(root.parts)] == root.parts:
            if len(parts) > len(root.parts) and re.fullmatch(
                    r"claude-[0-9]+", parts[len(root.parts)]):
                return True
    return False


def project_from_path(path):
    if not isinstance(path, str) or not path:
        return None
    path = path.split("/.claude/", 1)[0]
    review_repo = _review_repo_name(path)
    if review_repo:
        return _clip(review_repo, 200)
    name = _git_repo_name(path)
    if not name and _is_boundary(path):
        return None
    if not name:
        for component in reversed(Path(path).parts):
            match = re.fullmatch(r"(.+)-wt(?:-.+)?", component)
            if match:
                name = match.group(1)
                break
    return _clip(name or os.path.basename(path.rstrip("/")), 200) or None
