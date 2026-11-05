"""Adapter interface (docs/architecture.md §6). Adapters read another tool's files and return full records."""
import socket
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal, Protocol


def short_hostname():
    """Host name as `hostname -s` prints it (spec §5.1)."""
    return socket.gethostname().split(".")[0].lower()


@dataclass
class ScanResult:
    status: Literal["ok", "unavailable"]
    detail: str | None = None
    records: list[dict] = field(default_factory=list)


class Adapter(Protocol):
    source_id: str
    allowed_roots: list[Path]

    def available(self) -> bool:
        """Is the tool present on this machine (its state directory exists)."""

    def scan(self, now: datetime) -> ScanResult:
        """Read inputs (never write them) and return the full current records."""
