import argparse
import contextlib
import io
import json
import shlex
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from fleetglint import hooks, schema
from fleetglint.adapters.base import short_hostname

JST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 6, 12, 0, tzinfo=JST)
EXECUTABLE = "/opt/fleetglint/bin/fleetglint"
COMMAND = f"{EXECUTABLE} hooks record claude"


class _NotATty(io.StringIO):
    def isatty(self):
        return False


class HooksTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.state = self.dir / "state"
        self.settings = self.dir / "claude" / "settings.json"
        patcher = mock.patch.dict(os.environ, {
            "XDG_STATE_HOME": str(self.state),
            "XDG_CONFIG_HOME": str(self.dir / "config"),
            "CLAUDE_CONFIG_DIR": str(self.dir / "claude"),
        })
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_hooks(self, action, yes=True, config=None):
        args = argparse.Namespace(config=config, action=action, tool="claude", yes=yes)
        out = io.StringIO()
        with mock.patch.object(hooks, "executable_path", return_value=EXECUTABLE), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = hooks.run(args)
        return code, out.getvalue()

    def write_settings(self, data):
        self.settings.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(data, indent=2) + "\n"
        self.settings.write_text(text, encoding="utf-8")
        return text

    def installed_hook(self, data, event):
        for group in data["hooks"][event]:
            for hook in group["hooks"]:
                if hook.get("command") == COMMAND:
                    return hook
        return None

    def test_install_keeps_existing_hooks_and_is_idempotent(self):
        original = {
            "model": "claude-opus-5-5",
            "hooks": {
                "PreToolUse": [{"matcher": "Bash",
                               "hooks": [{"type": "command", "command": "echo hi",
                                          "timeout": 5}]}],
                "SessionStart": [{"matcher": "startup",
                                  "hooks": [{"type": "command", "command": "other",
                                             "timeout": 5}]}],
            },
        }
        before = self.write_settings(original)
        code, text = self.run_hooks("install")
        self.assertEqual(code, 0)
        self.assertIn("installed into", text)
        data = json.loads(self.settings.read_text(encoding="utf-8"))
        self.assertEqual(data["model"], "claude-opus-5-5")
        self.assertEqual(data["hooks"]["PreToolUse"], original["hooks"]["PreToolUse"])
        self.assertEqual(data["hooks"]["SessionStart"][0], original["hooks"]["SessionStart"][0])
        for event in hooks.EVENTS:
            self.assertEqual(self.installed_hook(data, event),
                             {"type": "command", "command": COMMAND, "timeout": 5})
            self.assertEqual(data["hooks"][event][-1]["matcher"], "")

        backups = list(self.settings.parent.glob("settings.json.fleetglint-backup-*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(encoding="utf-8"), before)

        installed = self.settings.read_bytes()
        code, text = self.run_hooks("install")
        self.assertEqual(code, 0)
        self.assertIn("nothing to do", text)
        self.assertEqual(self.settings.read_bytes(), installed)
        self.assertEqual(len(list(self.settings.parent.glob("settings.json.fleetglint-backup-*"))), 1)

        code, _ = self.run_hooks("uninstall")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(self.settings.read_text(encoding="utf-8")), original)

        code, text = self.run_hooks("uninstall")
        self.assertEqual(code, 0)
        self.assertIn("nothing to do", text)

    def test_invalid_json_is_refused(self):
        self.settings.parent.mkdir(parents=True, exist_ok=True)
        self.settings.write_text("{not json", encoding="utf-8")
        code, _ = self.run_hooks("install")
        self.assertEqual(code, 1)
        self.assertEqual(self.settings.read_text(encoding="utf-8"), "{not json")
        self.assertEqual(list(self.settings.parent.glob("*.fleetglint-backup-*")), [])

    def test_non_tty_without_yes_is_refused(self):
        original = self.write_settings({"hooks": {}})
        with mock.patch.object(hooks.sys, "stdin", _NotATty()):
            code, _ = self.run_hooks("install", yes=False)
        self.assertEqual(code, 1)
        self.assertEqual(self.settings.read_text(encoding="utf-8"), original)

    def test_backups_keep_permissions_and_never_overwrite_each_other(self):
        self.write_settings({"hooks": {}})
        os.chmod(self.settings, 0o600)
        previous = os.umask(0o022)
        try:
            with mock.patch.object(hooks, "datetime") as fake:
                fake.now.return_value = datetime(2026, 11, 6, 5, 0, 0, tzinfo=timezone.utc)
                self.assertEqual(self.run_hooks("install")[0], 0)
                self.assertEqual(self.run_hooks("uninstall")[0], 0)
        finally:
            os.umask(previous)
        backups = sorted(self.settings.parent.glob("settings.json.fleetglint-backup-*"))
        self.assertEqual(len(backups), 2)
        self.assertNotEqual(backups[0].name, backups[1].name)
        for backup in backups:
            self.assertEqual(backup.stat().st_mode & 0o777, 0o600, backup)
        self.assertEqual(self.settings.stat().st_mode & 0o777, 0o600)

    def test_settings_changed_while_waiting_aborts(self):
        self.write_settings({"hooks": {}})
        changed = json.dumps({"model": "changed"}, indent=2) + "\n"

        def confirm():
            self.settings.write_text(changed, encoding="utf-8")
            return True

        with mock.patch.object(hooks, "_confirm", side_effect=confirm):
            code, text = self.run_hooks("install", yes=False)
        self.assertEqual(code, 1)
        self.assertIn("changed while waiting; run again", text)
        self.assertEqual(self.settings.read_text(encoding="utf-8"), changed)
        self.assertEqual(list(self.settings.parent.glob("*.fleetglint-backup-*")), [])

    def test_settings_changed_during_backup_aborts(self):
        self.write_settings({"hooks": {}})
        changed = json.dumps({"model": "changed"}, indent=2) + "\n"
        real_backup = hooks._backup

        def backup(path, text, mode):
            self.settings.write_text(changed, encoding="utf-8")
            return real_backup(path, text, mode)

        with mock.patch.object(hooks, "_backup", side_effect=backup):
            code, text = self.run_hooks("install")
        self.assertEqual(code, 1)
        self.assertIn("changed while waiting; run again", text)
        self.assertEqual(self.settings.read_text(encoding="utf-8"), changed)

    def test_command_words_are_shell_quoted(self):
        config_file = "/a b/project$(touch pwned)/config.toml"
        self.write_settings({"hooks": {}})
        self.assertEqual(self.run_hooks("install", config=config_file)[0], 0)
        data = json.loads(self.settings.read_text(encoding="utf-8"))
        command = data["hooks"]["SessionStart"][0]["hooks"][0]["command"]
        self.assertEqual(shlex.split(command),
                         [EXECUTABLE, "--config", config_file, "hooks", "record", "claude"])
        self.assertEqual(self.run_hooks("uninstall", config=config_file)[0], 0)
        self.assertNotIn("hooks record claude", self.settings.read_text(encoding="utf-8"))

        with mock.patch.object(hooks.shutil, "which", return_value="/a b/fleetglint"):
            self.assertEqual(shlex.split(hooks.executable_path()), ["/a b/fleetglint"])
        with mock.patch.object(hooks.shutil, "which", return_value=None), \
                mock.patch.object(hooks.sys, "executable", "/a b/python3"):
            self.assertEqual(shlex.split(hooks.executable_path()),
                             ["/a b/python3", "-m", "fleetglint"])

    def test_install_and_uninstall_carry_the_config_path(self):
        config_file = self.dir / "config.toml"
        command = f"{EXECUTABLE} --config {config_file} hooks record claude"
        self.write_settings({"hooks": {}})
        self.assertEqual(self.run_hooks("install", config=str(config_file))[0], 0)
        data = json.loads(self.settings.read_text(encoding="utf-8"))
        for event in hooks.EVENTS:
            commands = {hook.get("command") for group in data["hooks"][event]
                        for hook in group["hooks"]}
            self.assertEqual(commands, {command})

        self.assertEqual(self.run_hooks("uninstall", config=str(config_file))[0], 0)
        data = json.loads(self.settings.read_text(encoding="utf-8"))
        self.assertNotIn(command, json.dumps(data))

    def sent(self, payload, now=NOW):
        code = hooks.record_claude(stream=io.BytesIO(json.dumps(payload).encode()), now=now)
        self.assertEqual(code, 0)

    def records(self):
        directory = self.state / "fleetglint" / "sources" / f"claude-hooks@{short_hostname()}"
        found = []
        for segment in sorted(directory.glob("*.ndjson")):
            for line in segment.read_text(encoding="utf-8").splitlines():
                found.append(json.loads(line))
        return found

    def latest(self, record_type, record_id):
        matches = [record for record in self.records()
                   if record["type"] == record_type and record["id"] == record_id]
        self.assertTrue(matches, record_id)
        return matches[-1]

    def test_session_start_and_end_records(self):
        self.sent({"hook_event_name": "SessionStart", "session_id": "sess-1",
                   "cwd": "/Users/me/Developer/atlas", "source": "startup",
                   "transcript_path": "/private/transcripts/sess-1.jsonl"})
        started = self.latest("session", "sess-1")
        self.assertEqual(started["source_id"], f"claude-hooks@{short_hostname()}")
        self.assertEqual(started["state"], "open")
        self.assertEqual(started["agent"], "claude-code")
        self.assertEqual(started["project"], "atlas")
        self.assertEqual(started["summary"], "start: startup")
        self.assertEqual(started["started_at"], NOW.isoformat())
        self.assertEqual(started["last_activity_at"], NOW.isoformat())

        self.sent({"hook_event_name": "SessionEnd", "session_id": "sess-1",
                   "cwd": "/Users/me/Developer/atlas", "reason": "clear",
                   "transcript_path": "/private/transcripts/sess-1.jsonl"})
        ended = self.latest("session", "sess-1")
        self.assertEqual(ended["state"], "ended")
        self.assertEqual(ended["started_at"], NOW.isoformat())
        self.assertEqual(ended["ended_at"], NOW.isoformat())
        self.assertEqual(ended["summary"], "end: clear")

        for record in self.records():
            self.assertEqual(schema.validate(record), [])
            self.assertNotIn("transcript", json.dumps(record))
            self.assertNotIn("/private", json.dumps(record))

    def test_a_second_session_start_keeps_the_first_started_at(self):
        self.sent({"hook_event_name": "SessionStart", "session_id": "sess-1",
                   "cwd": "/work/atlas", "source": "startup"})
        later = NOW + timedelta(minutes=10)
        self.sent({"hook_event_name": "SessionStart", "session_id": "sess-1",
                   "cwd": "/work/atlas", "source": "compact"}, now=later)
        record = self.latest("session", "sess-1")
        self.assertEqual(record["started_at"], NOW.isoformat())
        self.assertEqual(record["last_activity_at"], later.isoformat())
        self.assertEqual(record["summary"], "start: compact")
        self.assertEqual(schema.validate(record), [])

    def test_subagent_records(self):
        self.sent({"hook_event_name": "SessionStart", "session_id": "sess-1",
                   "cwd": "/work/atlas", "source": "resume"})
        self.sent({"hook_event_name": "SubagentStart", "session_id": "sess-1",
                   "agent_id": "agent-abc", "agent_type": "Explore", "cwd": "/work/atlas"})
        started = self.latest("session", "agent-abc")
        self.assertEqual(started["state"], "open")
        self.assertEqual(started["parent_session"], {"type": "session", "id": "sess-1"})

        self.sent({"hook_event_name": "SubagentStop", "session_id": "sess-1",
                   "agent_id": "agent-abc", "agent_type": "Explore"})
        ended = self.latest("session", "agent-abc")
        self.assertEqual(ended["state"], "ended")
        self.assertEqual(ended["started_at"], NOW.isoformat())
        self.assertEqual(ended["ended_at"], NOW.isoformat())
        for record in self.records():
            self.assertEqual(schema.validate(record), [])

    def test_subagent_without_an_id_is_skipped(self):
        self.sent({"hook_event_name": "SessionStart", "session_id": "sess-1",
                   "cwd": "/work/atlas", "source": "startup"})
        before = len(self.records())
        self.sent({"hook_event_name": "SubagentStart", "session_id": "sess-1"})
        self.assertEqual(len(self.records()), before)

    def test_garbage_stdin_exits_zero_and_logs(self):
        code = hooks.record_claude(stream=io.BytesIO(b"not json at all"), now=NOW)
        self.assertEqual(code, 0)
        log = self.state / "fleetglint" / "hooks.log"
        self.assertTrue(log.exists())
        text = log.read_text(encoding="utf-8")
        self.assertIn("invalid JSON", text)
        self.assertNotIn("not json at all", text)
        self.assertEqual(self.records(), [])


if __name__ == "__main__":
    unittest.main()
