import os
import subprocess
import sys
import unittest
from datetime import datetime, timedelta, timezone

from fleetglint import liveness
from fleetglint.adapters.base import short_hostname

NOW = datetime(2026, 11, 6, 3, 0, tzinfo=timezone.utc)


def ts(seconds_ago=0):
    return (NOW - timedelta(seconds=seconds_ago)).isoformat()


def record(**fields):
    base = {"v": 1, "type": "run", "id": "r1", "source_id": "src", "updated_at": ts()}
    base.update(fields)
    return base


class FakeChecker:
    def __init__(self, answer):
        self.answer = answer
        self.calls = []

    def check(self, process):
        self.calls.append(process)
        return self.answer


def show(rec, **kwargs):
    return liveness.display(rec, NOW, **kwargs)


class IsTerminalTest(unittest.TestCase):
    def test_terminal_states(self):
        for value in ("done", "failed", "cancelled", "acked", "ended"):
            with self.subTest(state=value):
                self.assertTrue(liveness.is_terminal({"state": value}))

    def test_non_terminal_states(self):
        for value in ("queued", "running", "waiting", "unknown", "open", "recent", "idle"):
            with self.subTest(state=value):
                self.assertFalse(liveness.is_terminal({"state": value}))

    def test_missing_state(self):
        self.assertFalse(liveness.is_terminal({}))


class DisplayTableTest(unittest.TestCase):
    def test_current_observed_state_is_shown(self):
        for value in ("queued", "running", "waiting"):
            with self.subTest(state=value):
                rec = record(state=value, observed_at=ts(10))
                self.assertEqual(show(rec), liveness.Display(value, "observed", 10))

    def test_expired_record_is_stale(self):
        rec = record(state="running", observed_at=ts(1000))
        self.assertEqual(show(rec), liveness.Display("stale", "expired", 1000))

    def test_staleness_boundary(self):
        self.assertEqual(show(record(state="running", observed_at=ts(899))).state, "running")
        self.assertEqual(show(record(state="running", observed_at=ts(900))).state, "stale")

    def test_record_stale_after_s_overrides_the_default(self):
        rec = record(state="running", observed_at=ts(31), stale_after_s=30)
        self.assertEqual(show(rec), liveness.Display("stale", "expired", 31))
        rec["observed_at"] = ts(29)
        self.assertEqual(show(rec), liveness.Display("running", "observed", 29))

    def test_default_stale_after_s_argument(self):
        rec = record(state="running", observed_at=ts(61))
        self.assertEqual(show(rec, default_stale_after_s=60).state, "stale")
        self.assertEqual(show(rec, default_stale_after_s=90).state, "running")

    def test_terminal_states_keep_their_state(self):
        for value in ("done", "failed", "cancelled"):
            with self.subTest(state=value):
                rec = record(state=value, observed_at=ts(5))
                self.assertEqual(show(rec), liveness.Display(value, "terminal", None))

    def test_acked_inbox_item_is_terminal(self):
        rec = record(type="inbox_item", state="acked", observed_at=ts(5))
        self.assertEqual(show(rec), liveness.Display("acked", "terminal", None))

    def test_ended_session_is_terminal(self):
        rec = record(type="session", state="ended", last_activity_at=ts(5))
        self.assertEqual(show(rec), liveness.Display("ended", "terminal", None))

    def test_unknown_writer_state(self):
        rec = record(state="unknown", observed_at=ts(1))
        self.assertEqual(show(rec), liveness.Display("unknown", "writer_unknown", 1))

    def test_unknown_writer_state_wins_over_a_live_process(self):
        rec = record(state="unknown", observed_at=ts(1), process={"host": "h", "pid": 1})
        self.assertEqual(show(rec, process_checker=FakeChecker(True)),
                         liveness.Display("unknown", "writer_unknown", 1))

    def test_future_timestamp_gives_age_zero(self):
        rec = record(state="running", observed_at=(NOW + timedelta(seconds=100)).isoformat())
        self.assertEqual(show(rec), liveness.Display("running", "observed", 0))

    def test_z_suffix_is_parsed(self):
        rec = record(state="running", observed_at="2026-11-06T02:59:50Z")
        self.assertEqual(show(rec), liveness.Display("running", "observed", 10))

    def test_missing_observed_at_is_stale(self):
        rec = record(state="running")
        self.assertEqual(show(rec), liveness.Display("stale", "expired", None))


class ProcessCheckDisplayTest(unittest.TestCase):
    def process_record(self, observed_at):
        return record(state="running", observed_at=observed_at,
                      process={"host": "h", "pid": 42})

    def test_live_process_is_current_evidence(self):
        checker = FakeChecker(True)
        rec = self.process_record(ts(5000))
        self.assertEqual(show(rec, process_checker=checker),
                         liveness.Display("running", "process", 5000))
        self.assertEqual(len(checker.calls), 1)

    def test_gone_process_is_lost(self):
        rec = self.process_record(ts(5000))
        self.assertEqual(show(rec, process_checker=FakeChecker(False)),
                         liveness.Display("lost", "process_gone", 5000))

    def test_uncheckable_process_falls_back_to_observed_at(self):
        self.assertEqual(show(self.process_record(ts(10)), process_checker=FakeChecker(None)),
                         liveness.Display("running", "observed", 10))
        self.assertEqual(show(self.process_record(ts(5000)), process_checker=FakeChecker(None)),
                         liveness.Display("stale", "expired", 5000))

    def test_other_host_falls_back_to_observed_at(self):
        checker = liveness.ProcessChecker(hostname="some-other-host")
        self.assertEqual(show(self.process_record(ts(10)), process_checker=checker),
                         liveness.Display("running", "observed", 10))

    def test_no_process_means_no_check(self):
        checker = FakeChecker(True)
        rec = record(state="running", observed_at=ts(10))
        show(rec, process_checker=checker)
        self.assertEqual(checker.calls, [])


class SourceProblemTest(unittest.TestCase):
    def test_non_terminal_records_become_unknown(self):
        rec = record(state="running", observed_at=ts(10))
        self.assertEqual(show(rec, source_ok=False),
                         liveness.Display("unknown", "source_problem", 10))

    def test_terminal_records_are_unaffected(self):
        rec = record(state="done", observed_at=ts(10))
        self.assertEqual(show(rec, source_ok=False), liveness.Display("done", "terminal", None))

    def test_inbox_items_and_sessions_become_unknown(self):
        inbox = record(type="inbox_item", state="open", observed_at=ts(10))
        self.assertEqual(show(inbox, source_ok=False),
                         liveness.Display("unknown", "source_problem", 10))
        session = record(type="session", state="open", last_activity_at=ts(10))
        self.assertEqual(show(session, source_ok=False),
                         liveness.Display("unknown", "source_problem", 10))


class InboxDisplayTest(unittest.TestCase):
    def test_open_item_is_never_stale(self):
        rec = record(type="inbox_item", state="open", observed_at=ts(100_000))
        self.assertEqual(show(rec), liveness.Display("open", "observed", 100_000))

    def test_acked_item(self):
        rec = record(type="inbox_item", state="acked", observed_at=ts(100_000))
        self.assertEqual(show(rec), liveness.Display("acked", "terminal", None))


class SessionDisplayTest(unittest.TestCase):
    def test_recent_session(self):
        rec = record(type="session", state="open", last_activity_at=ts(10))
        self.assertEqual(show(rec), liveness.Display("recent", "activity", 10))

    def test_idle_session(self):
        rec = record(type="session", state="open", last_activity_at=ts(901))
        self.assertEqual(show(rec), liveness.Display("idle", "activity", 901))

    def test_unknown_session_state_still_uses_activity(self):
        rec = record(type="session", state="unknown", last_activity_at=ts(10))
        self.assertEqual(show(rec), liveness.Display("recent", "activity", 10))

    def test_session_stale_after_s(self):
        rec = record(type="session", state="open", last_activity_at=ts(31), stale_after_s=30)
        self.assertEqual(show(rec), liveness.Display("idle", "activity", 31))

    def test_missing_last_activity_is_idle(self):
        rec = record(type="session", state="open")
        self.assertEqual(show(rec), liveness.Display("idle", "activity", None))


class ProcessCheckerTest(unittest.TestCase):
    def setUp(self):
        self.checker = liveness.ProcessChecker()

    def test_other_host_is_uncheckable(self):
        self.assertIsNone(self.checker.check({"host": "some-other-host", "pid": os.getpid()}))

    def test_hostname_comparison_is_case_insensitive(self):
        if liveness._process_start_time(os.getpid()) is None:
            self.skipTest("no process start-time implementation on this platform")
        checker = liveness.ProcessChecker(hostname=short_hostname().upper())
        self.assertIs(checker.check({"host": short_hostname(), "pid": os.getpid()}), True)

    def test_non_positive_pid_is_gone(self):
        for pid in (0, -1):
            with self.subTest(pid=pid):
                self.assertIs(self.checker.check({"host": self.checker.hostname, "pid": pid}), False)

    def test_live_process_matches_its_start_time(self):
        started = liveness._process_start_time(os.getpid())
        if started is None:
            self.skipTest("no process start-time implementation on this platform")
        proc = {"host": short_hostname(), "pid": os.getpid(),
                "start_time": datetime.fromtimestamp(started, timezone.utc).isoformat()}
        self.assertIs(self.checker.check(proc), True)
        proc["start_time"] = datetime.fromtimestamp(started + 1, timezone.utc).isoformat()
        self.assertIs(self.checker.check(proc), True)
        proc["start_time"] = datetime.fromtimestamp(started + 100, timezone.utc).isoformat()
        self.assertIs(self.checker.check(proc), False)

    def test_dead_process(self):
        if liveness._process_start_time(os.getpid()) is None:
            self.skipTest("no process start-time implementation on this platform")
        child = subprocess.Popen([sys.executable, "-c", "pass"])
        child.wait()
        self.assertIs(self.checker.check({"host": short_hostname(), "pid": child.pid}), False)


if __name__ == "__main__":
    unittest.main()
