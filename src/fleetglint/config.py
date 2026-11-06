"""Configuration file, defaults and paths (docs/architecture.md §7)."""
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


def xdg_dir(env, fallback):
    value = os.environ.get(env)
    return Path(value) if value else Path.home() / fallback


def state_dir():
    return xdg_dir("XDG_STATE_HOME", ".local/state") / "fleetglint"


def config_path():
    return xdg_dir("XDG_CONFIG_HOME", ".config") / "fleetglint" / "config.toml"


def expand(path):
    return Path(os.path.expanduser(str(path))).absolute()


@dataclass
class HarnessAdapterConfig:
    enabled: str = "auto"  # auto | true | false
    state_dir: Path = field(default_factory=lambda: expand("~/.local/state"))


def _env_dir(env, sub, fallback):
    value = os.environ.get(env)
    return expand(Path(value) / sub) if value else expand(fallback)


@dataclass
class ClaudeCodeAdapterConfig:
    enabled: str = "auto"
    dir: Path = field(default_factory=lambda: _env_dir("CLAUDE_CONFIG_DIR", "projects", "~/.claude/projects"))


@dataclass
class CodexAdapterConfig:
    enabled: str = "auto"
    dir: Path = field(default_factory=lambda: _env_dir("CODEX_HOME", "", "~/.codex"))


@dataclass
class Config:
    port: int = 8765
    roots: list[Path] = field(default_factory=lambda: [state_dir() / "sources"])
    poll_s: float = 2
    adapter_poll_s: float = 5
    default_stale_after_s: int = 900
    window_hours: int = 24
    viewer_roles: list[str] = field(default_factory=lambda: ["owner"])
    needs_you_hours: int = 24
    inbox_old_after_s: int = 7200
    segment_days: int = 30
    abandon_days: int = 90
    history_days: int = 30
    allowed_roots: list[Path] = field(default_factory=list)
    max_tail_kib: int = 64
    harness: HarnessAdapterConfig = field(default_factory=HarnessAdapterConfig)
    claude_code: ClaudeCodeAdapterConfig = field(default_factory=ClaudeCodeAdapterConfig)
    codex: CodexAdapterConfig = field(default_factory=CodexAdapterConfig)
    db_path: Path = field(default_factory=lambda: state_dir() / "fleetglint.sqlite")


class ConfigError(Exception):
    pass


def _get(table, key, kind, default):
    if key not in table:
        return default
    value = table[key]
    if kind is float and isinstance(value, int) and not isinstance(value, bool):
        value = float(value)
    if not isinstance(value, kind) or isinstance(value, bool) and kind is not bool:
        raise ConfigError(f"{key}: expected {kind.__name__}, got {type(value).__name__}")
    return value


def load(path=None):
    """Read the config file (missing file = all defaults) and return a Config."""
    path = expand(path) if path else config_path()
    cfg = Config()
    if not path.exists():
        return cfg
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"{path}: {exc}") from exc

    server = data.get("server", {})
    if "host" in server and server["host"] != "127.0.0.1":
        raise ConfigError("server.host: Fleetglint only listens on 127.0.0.1")
    cfg.port = _get(server, "port", int, cfg.port)
    if not 0 < cfg.port < 65536:
        raise ConfigError("server.port: out of range")

    ingest = data.get("ingest", {})
    if "roots" in ingest:
        cfg.roots = [expand(p) for p in _get(ingest, "roots", list, [])]
    cfg.poll_s = _get(ingest, "poll_s", float, cfg.poll_s)
    cfg.adapter_poll_s = _get(ingest, "adapter_poll_s", float, cfg.adapter_poll_s)
    cfg.default_stale_after_s = _get(ingest, "default_stale_after_s", int, cfg.default_stale_after_s)
    cfg.window_hours = _get(ingest, "window_hours", int, cfg.window_hours)
    if "db_path" in ingest:
        cfg.db_path = expand(_get(ingest, "db_path", str, ""))

    ui = data.get("ui", {})
    cfg.viewer_roles = _get(ui, "viewer_roles", list, cfg.viewer_roles)
    if any(not isinstance(role, str) for role in cfg.viewer_roles):
        raise ConfigError("ui.viewer_roles: expected a list of strings")
    cfg.needs_you_hours = _get(ui, "needs_you_hours", int, cfg.needs_you_hours)
    cfg.inbox_old_after_s = _get(ui, "inbox_old_after_s", int, cfg.inbox_old_after_s)

    retention = data.get("retention", {})
    cfg.segment_days = _get(retention, "segment_days", int, cfg.segment_days)
    cfg.abandon_days = _get(retention, "abandon_days", int, cfg.abandon_days)
    cfg.history_days = _get(retention, "history_days", int, cfg.history_days)
    if cfg.abandon_days < cfg.segment_days:
        raise ConfigError("retention.abandon_days must not be shorter than retention.segment_days")

    files = data.get("files", {})
    cfg.allowed_roots = [expand(p) for p in _get(files, "allowed_roots", list, [])]
    cfg.max_tail_kib = _get(files, "max_tail_kib", int, cfg.max_tail_kib)

    adapters = data.get("adapters", {})
    for name, target, dir_key in (("tachiko_harness", cfg.harness, "state_dir"),
                                  ("claude_code", cfg.claude_code, "dir"),
                                  ("codex", cfg.codex, "dir")):
        table = adapters.get(name, {})
        enabled = table.get("enabled", "auto")
        if enabled is True or enabled is False:
            enabled = "true" if enabled else "false"
        if enabled not in ("auto", "true", "false"):
            raise ConfigError(f"adapters.{name}.enabled: auto, true or false")
        target.enabled = enabled
        if dir_key in table:
            setattr(target, dir_key, expand(_get(table, dir_key, str, "")))
    return cfg
