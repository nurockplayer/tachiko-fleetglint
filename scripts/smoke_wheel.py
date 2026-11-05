"""Smoke test an installed Fleetglint wheel: serve, UI, emit, clean SIGTERM exit.

Usage: python scripts/smoke_wheel.py <path to the fleetglint executable>

Standard library only. Everything runs in a temporary HOME and state directory, so the
real user's data is never read or written.
"""
import http.client
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

CONFIG = """[ingest]
poll_s = 0.1
adapter_poll_s = 0.1
"""
TIMEOUT_S = 15


def _drain(stream, sink):
    try:
        for line in stream:
            sink.append(line)
    except (OSError, ValueError):
        pass


def _start(exe, config_path, env):
    proc = subprocess.Popen(
        [str(exe), "--config", str(config_path), "serve", "--port", "0"],
        env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, bufsize=1)
    stdout, stderr = [], []
    for stream, sink in ((proc.stdout, stdout), (proc.stderr, stderr)):
        threading.Thread(target=_drain, args=(stream, sink), daemon=True).start()
    deadline = time.monotonic() + TIMEOUT_S
    while time.monotonic() < deadline:
        match = re.search(r"http://127\.0\.0\.1:(\d+)/", "".join(stdout))
        if match:
            return proc, int(match.group(1)), stdout, stderr
        if proc.poll() is not None:
            raise AssertionError(f"serve exited with {proc.returncode}: {''.join(stderr)}")
        time.sleep(0.02)
    raise AssertionError(f"serve printed no URL within {TIMEOUT_S} s: {''.join(stderr)}")


def _get(port, path):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        conn.request("GET", path)
        response = conn.getresponse()
        return response.status, response.read()
    finally:
        conn.close()


def _emit(exe, config_path, env, record):
    result = subprocess.run(
        [str(exe), "--config", str(config_path), "emit"],
        input=json.dumps(record).encode("utf-8"), env=env, capture_output=True, timeout=30)
    if result.returncode != 0:
        raise AssertionError(f"emit exited with {result.returncode}: "
                             f"{result.stderr.decode('utf-8', 'replace')}")


def _run(exe):
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        for name in ("home", "state", "config", "claude", "codex"):
            (base / name).mkdir()
        config_path = base / "config" / "config.toml"
        config_path.write_text(CONFIG, encoding="utf-8")
        env = os.environ.copy()
        env.update({
            "HOME": str(base / "home"),
            "XDG_STATE_HOME": str(base / "state"),
            "XDG_CONFIG_HOME": str(base / "config"),
            "CLAUDE_CONFIG_DIR": str(base / "claude"),
            "CODEX_HOME": str(base / "codex"),
        })
        env.pop("PYTHONPATH", None)

        proc, port, stdout, stderr = _start(exe, config_path, env)
        try:
            status, body = _get(port, "/")
            assert status == 200, f"GET / returned {status}"
            assert b"Fleetglint" in body, "GET / does not mention Fleetglint"

            assets = re.findall(rb'(?:src|href)="(/assets/[^"]+)"', body)
            assert assets, "GET / links no built asset (the wheel does not ship the UI)"
            asset = assets[0].decode("utf-8")
            status, asset_body = _get(port, asset)
            assert status == 200 and asset_body, f"GET {asset} returned {status}"

            stamp = datetime.now(timezone.utc).astimezone().isoformat()
            record = {"v": 1, "type": "run", "id": "wheel-smoke",
                      "source_id": "smoke@release", "updated_at": stamp,
                      "observed_at": stamp, "state": "running",
                      "agent": "codex-cli", "started_at": stamp}
            _emit(exe, config_path, env, record)

            deadline = time.monotonic() + TIMEOUT_S
            seen = False
            while time.monotonic() < deadline:
                status, snapshot_body = _get(port, "/api/snapshot")
                if status == 200:
                    snapshot = json.loads(snapshot_body)
                    seen = any(item["ref"]["id"] == "wheel-smoke"
                               for item in snapshot["runs"])
                    if seen:
                        break
                time.sleep(0.05)
            assert seen, "the emitted record never appeared in /api/snapshot"
        finally:
            if proc.poll() is None:
                proc.send_signal(signal.SIGTERM)
            try:
                proc.wait(timeout=TIMEOUT_S)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        assert proc.returncode == 0, (f"serve exited with {proc.returncode} after SIGTERM: "
                                      f"{''.join(stderr)}")


def main(argv):
    if len(argv) != 2:
        print("usage: smoke_wheel.py <path to the fleetglint executable>", file=sys.stderr)
        return 2
    exe = Path(argv[1])
    if not exe.exists():
        print(f"smoke_wheel.py: {exe} does not exist", file=sys.stderr)
        return 2
    try:
        _run(exe)
    except AssertionError as exc:
        print(f"smoke_wheel.py: FAIL: {exc}", file=sys.stderr)
        return 1
    print("smoke_wheel.py: wheel serves the UI, ingests an emitted record and stops on SIGTERM")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
