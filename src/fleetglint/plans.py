"""Opt-in, bounded background reader of harness plan-check JSON output v1."""
import json
import os
from pathlib import Path
import selectors
import shutil
import signal
import subprocess
import threading
import time
from datetime import datetime

from fleetglint.redact import redact

REFRESH_S = 15
EXPIRY_S = 180
TIMEOUT_S = 30
MAX_OUTPUT = 1024 * 1024


def _redact(value):
    if isinstance(value, str):
        return redact(value)[0]
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, dict):
        return {redact(key)[0]: _redact(item) for key, item in value.items()}
    return value


def _run(argv, timeout, limit, stop):
    """Drain both pipes within one byte/time budget; kill the process group on exit."""
    process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               start_new_session=True)
    output = {process.stdout: bytearray(), process.stderr: bytearray()}
    deadline = time.monotonic() + timeout
    total = 0
    try:
        with selectors.DefaultSelector() as selector:
            for pipe in output:
                selector.register(pipe, selectors.EVENT_READ)
            while selector.get_map():
                if stop.is_set():
                    raise OSError("plan refresh stopped")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise OSError(f"command timed out after {timeout} seconds")
                for key, _ in selector.select(min(remaining, 0.1)):
                    chunk = os.read(key.fd, 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    total += len(chunk)
                    if total > limit:
                        raise OSError(f"command output exceeded {limit} bytes")
                    output[key.fileobj].extend(chunk)
            code = process.wait(timeout=max(0.001, deadline - time.monotonic()))
        return code, bytes(output[process.stdout]), bytes(output[process.stderr])
    finally:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
        for pipe in output:
            pipe.close()


class Plans:
    def __init__(self, paths=(), *, timeout=TIMEOUT_S, expiry=EXPIRY_S):
        self.paths = [os.path.expanduser(path) for path in paths]
        self.timeout, self.expiry = timeout, expiry
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._cache = {}
        self._rows = [{"path": path, "state": "pending", "checked_at": None,
                       "file_modified_at": None, "refreshing": True} for path in self.paths]

    def start(self):
        if self.paths:
            self._thread = threading.Thread(target=self._loop, daemon=True, name="plans")
            self._thread.start()

    def close(self):
        self._stop.set()
        if self._thread:
            self._thread.join()

    def snapshot(self):
        # Rows are replaced, never mutated: HTTP does no filesystem or subprocess work.
        with self._lock:
            return {"api": 1, "refresh_s": REFRESH_S, "plans": list(self._rows)}

    def _loop(self):
        while not self._stop.is_set():
            self.refresh()
            self._stop.wait(REFRESH_S)

    def _publish(self, index, row):
        with self._lock:
            self._rows[index] = _redact(row)

    def refresh(self):
        """Called only by the background worker (or explicitly by tests)."""
        if not self.paths:
            return
        executable = shutil.which("plan-check")
        git = shutil.which("git")
        for index, path in enumerate(self.paths):
            if self._stop.is_set():
                return
            modified = None
            key = (path, None, None)
            try:
                resolved = Path(path).resolve()
                if resolved.is_dir():
                    resolved = (resolved / "plan.yaml").resolve()
                try:
                    stat = resolved.stat()
                    stamp = (stat.st_mtime_ns, stat.st_size)
                    modified = datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat()
                except FileNotFoundError:
                    stamp = None
                head = None
                if git:
                    code, stdout, _ = _run([git, "-C", str(resolved.parent), "rev-parse", "HEAD"],
                                           5, MAX_OUTPUT, self._stop)
                    head = stdout.decode().strip() if code == 0 else None
                key = (str(resolved), stamp, head)
                cached = self._cache.get(path)
                if cached and cached[0] == key and time.monotonic() - cached[1] < self.expiry:
                    continue
                self._publish(index, {**self._rows[index], "refreshing": True})
                if executable is None:
                    result = {"state": "unavailable", "errors": ["plan-check is not on PATH"]}
                else:
                    result = self._check(executable, path)
            except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as error:
                result = {"state": "failed", "errors": [str(error)]}
            row = {"path": path, "file_modified_at": modified, "refreshing": False,
                   "checked_at": datetime.now().astimezone().isoformat(), **result}
            self._cache[path] = (key, time.monotonic())
            self._publish(index, row)

    def _check(self, executable, path):
        code, stdout, stderr = _run([executable, path, "--json"], self.timeout,
                                    MAX_OUTPUT, self._stop)
        report = json.loads(stdout)
        if not isinstance(report, dict) or report.get("output_version") != 1:
            raise ValueError("expected plan-check JSON output v1")
        if code == 1 or report.get("valid") is False and code == 0:
            return {"state": "invalid", "errors": report["errors"]}
        if code != 0:
            return {"state": "failed", "errors": report.get("errors") or
                    [stderr.decode(errors="replace") or f"plan-check exited {code}"]}
        if report.get("valid") is not True:
            raise ValueError("plan-check did not report valid: true")
        plan = report.get("plan")
        source = {stream["id"]: stream for stream in plan.get("workstreams", [])} if plan else {}
        streams = []
        for stream in report["workstreams"]:
            text = source.get(stream["id"], {})
            criteria = {row["id"]: row for row in text.get("criteria", [])}
            streams.append({**text, **stream, "criteria": [
                {**criteria.get(row["id"], {}), **row} for row in stream["criteria"]]})
        return {"state": "ok", "project": report["project"], "plan_state": report["state"],
                "counts": report["counts"], "workstreams": streams,
                "owner_decisions": plan.get("owner_decisions", []) if plan else [],
                "text_available": plan is not None}
