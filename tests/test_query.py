"""Tests for fleetglint.query: the board JSON of docs/architecture.md §4."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from fleetglint import config, ingest, query, store

JST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 6, 4, 0, tzinfo=JST)
SECRET = "sk-" + "a1B2c3D4e5F6g7H8i9J0k1L2"
EXAMPLES = Path(__file__).resolve().parent.parent / "examples" / "v1" / "valid"

SNAPSHOT_KEYS = {"api", "generated_at", "server", "window_hours", "sources", "counts",
                 "runs", "jobs", "inbox", "sessions", "attention", "truncated", "demo"}
SUMMARY_BASE_KEYS = {"ref", "state", "display_state", "evidence", "updated_at",
                     "observed_at", "project", "title", "links"}
RUN_KEYS = SUMMARY_BASE_KEYS | {"agent", "model", "provider", "effort", "role_id",
                                "session_id", "started_at", "ended_at", "exit_code",
                                "summary", "parent_run", "resume_of", "waits_on"}
JOB_KEYS = SUMMARY_BASE_KEYS | {"kind", "command_summary", "run", "role_id", "started_at",
                                "ended_at", "exit_code", "signal", "summary", "log", "result"}
INBOX_KEYS = SUMMARY_BASE_KEYS | {"role_id", "kind", "subject", "outcome", "action_required",
                                  "created_at", "acked_at", "detail", "blocks_retention"}
SESSION_KEYS = SUMMARY_BASE_KEYS | {"agent", "model", "models", "provider", "effort",
                                    "role_id", "started_at", "last_activity_at", "ended_at",
                                    "turn_open", "entries", "parent_session", "usage"}
EVIDENCE_KEYS = {"kind", "age_s", "detail"}
REF_KEYS = {"type", "id", "source_id"}
ATTENTION_KEYS = {"reason", "who", "subject", "source_id", "text"}
RECORD_KEYS = {"api", "generated_at", "record", "full", "relations", "history", "usage"}
RELATION_KEYS = {"parent", "resume_of", "children", "resumed_by", "jobs", "inbox",
                 "waited_on_by"}
BOARD_KEYS = {"api", "generated_at", "server", "window_hours", "inbox_old_after_s", "demo", "sources",
              "capabilities", "counts", "needs_you", "lead_inbox", "queued", "waiting", "running",
              "exceptions", "recent", "sessions", "sessions_total", "truncated", "projects"}
BOARD_COUNT_KEYS = {"needs_you", "queued", "waiting", "running", "lead_inbox_open", "lead_inbox_old",
                    "process_gone", "out_of_date", "unverified_recent", "failed_recent",
                    "older_unverified", "sessions_recent"}
BOARD_TRUNCATED_KEYS = {"queued", "waiting", "running", "exceptions", "recent", "lead_inbox"}
LEAD_INBOX_KEYS = {"role_id", "open", "old", "oldest_age_s", "action_required", "items", "by_project"}
WORK_BOARD_KEYS = RUN_KEYS | {"started_age_s", "section_reason"}
JOB_BOARD_KEYS = JOB_KEYS | {"started_age_s", "section_reason"}
INBOX_BOARD_KEYS = INBOX_KEYS | {"age_s"}


def stamp(**delta):
    return (NOW + timedelta(**delta)).isoformat()


def run(id="r1", state="running", source_id="work@mbp", **extra):
    # `started_at` is required by schema/v1 for every non-queued/unknown state.
    record = {"v": 1, "type": "run", "id": id, "source_id": source_id,
              "updated_at": stamp(seconds=-30), "state": state, "agent": "codex-cli",
              "started_at": stamp(minutes=-10)}
    record.update(extra)
    return record


def job(id="j1", state="running", source_id="work@mbp", **extra):
    record = {"v": 1, "type": "job", "id": id, "source_id": source_id,
              "updated_at": stamp(seconds=-30), "state": state,
              "command_summary": "orb-test", "started_at": stamp(minutes=-10)}
    record.update(extra)
    return record


def inbox(id="i1", state="open", source_id="work@mbp", **extra):
    record = {"v": 1, "type": "inbox_item", "id": id, "source_id": source_id,
              "updated_at": stamp(seconds=-30), "state": state, "role_id": "lead",
              "kind": "job_finished", "created_at": stamp(seconds=-60),
              "subject": {"type": "job", "id": "j1"}}
    record.update(extra)
    return record


def session(id="s1", state="unknown", source_id="work@mbp", **extra):
    record = {"v": 1, "type": "session", "id": id, "source_id": source_id,
              "updated_at": stamp(seconds=-30), "state": state, "agent": "claude-code",
              "last_activity_at": stamp(seconds=-30)}
    record.update(extra)
    return record


def keys(item):
    return set(item)


class QueryTest(unittest.TestCase):
    """A temp database built by the real Ingestor, read through QueryBackend."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.root = self.dir / "sources"
        self.root.mkdir()
        cfg = config.Config()
        cfg.roots = [self.root]
        cfg.db_path = self.dir / "db.sqlite"
        self.disable_adapters(cfg)
        self.cfg = cfg
        self.conn = store.open_db(cfg.db_path)
        self.addCleanup(self.conn.close)
        self.ing = ingest.Ingestor(self.conn, cfg, clock=lambda: NOW)

        self.log_path = self.root / "work@mbp" / "logs" / "j1.log"
        self.log_path.parent.mkdir(parents=True)
        self.log_path.write_text("start\n" + SECRET + "\ndone\n", encoding="utf-8")
        self.outside_path = self.dir / "outside.log"
        self.outside_path.write_text("outside\n", encoding="utf-8")

        # Two versions of w-1: the second is an observation refresh.
        self.write("work@mbp", [
            run("lead-1", role_id="lead", title="lead session", project="fleetglint",
                updated_at=stamp(seconds=-90), observed_at=stamp(seconds=-60),
                started_at=stamp(minutes=-10), model="claude-opus-5-5",
                provider="anthropic", effort="high", session_id="sess-1",
                summary="lead summary", usage={"basis": "measured", "input_tokens": 10}),
            run("w-1", role_id="worker", title="worker task",
                updated_at=stamp(seconds=-40), observed_at=stamp(seconds=-40),
                parent_run={"type": "run", "id": "lead-1"}),
            run("w-1", role_id="worker", title="worker task",
                updated_at=stamp(seconds=-30), observed_at=stamp(seconds=-10),
                parent_run={"type": "run", "id": "lead-1"},
                links=[{"label": "log", "path": str(self.log_path)}]),
            run("waiting-1", state="waiting",
                updated_at=stamp(seconds=-20), observed_at=stamp(seconds=-20)),
            run("resumed-1", state="waiting", resume_of={"type": "run", "id": "lead-1"},
                updated_at=stamp(seconds=-15), observed_at=stamp(seconds=-15),
                waits_on=[{"type": "external", "kind": "github_pr", "key": "owner/repo#1",
                           "url": "https://github.com/owner/repo/pull/1"},
                          {"type": "run", "id": "w-1"}]),
            run("stale-1", updated_at=stamp(minutes=-42), observed_at=stamp(minutes=-42),
                role_id="lead", title="stale worker"),
            run("unknown-1", state="unknown", updated_at=stamp(minutes=-5)),
            run("done-1", state="done", updated_at=stamp(minutes=-10),
                ended_at=stamp(minutes=-10), exit_code=0),
            run("old-done", state="done", updated_at=stamp(hours=-30),
                ended_at=stamp(hours=-30)),
        ])
        self.write("work@mbp", [
            job("j-1", run={"type": "run", "id": "lead-1"},
                updated_at=stamp(seconds=-25), observed_at=stamp(seconds=-25),
                log_path=str(self.log_path)),
            job("j-done", state="done", run={"type": "run", "id": "lead-1"},
                updated_at=stamp(minutes=-20), ended_at=stamp(minutes=-20), exit_code=0),
            job("j-old", state="failed", updated_at=stamp(hours=-30),
                ended_at=stamp(hours=-30)),
        ], seq=2)
        self.write("work@mbp", [
            inbox("i-action", role_id="lead", action_required=True,
                  subject={"type": "job", "id": "j-1"}, outcome="done",
                  detail="review the PR", updated_at=stamp(minutes=-20)),
            inbox("i-open", role_id="worker", kind="message",
                  subject={"type": "run", "id": "w-1"}, detail="heads up",
                  updated_at=stamp(minutes=-12)),
            inbox("i-acked", state="acked", role_id="lead", kind="url",
                  subject={"type": "external", "kind": "url",
                           "url": "https://example.com/1"},
                  updated_at=stamp(minutes=-5), acked_at=stamp(minutes=-5)),
            inbox("i-old-acked", state="acked", updated_at=stamp(hours=-30),
                  acked_at=stamp(hours=-30)),
        ], seq=3)
        self.write("work@mbp", [
            session("sess-recent", role_id="lead", project="fleetglint",
                    title="fleetglint-lead", model="claude-opus-5-5",
                    models=["claude-opus-5-5"], entries=10,
                    last_activity_at=stamp(seconds=-30),
                    usage={"basis": "measured", "output_tokens": 5}),
            session("sess-child", last_activity_at=stamp(minutes=-1),
                    parent_session={"type": "session", "id": "sess-recent"}),
            session("sess-idle", agent="codex-cli", last_activity_at=stamp(minutes=-120),
                    updated_at=stamp(minutes=-120)),
            session("sess-ended", state="ended", last_activity_at=stamp(minutes=-180),
                    updated_at=stamp(minutes=-180), ended_at=stamp(minutes=-180)),
            session("sess-old", last_activity_at=stamp(hours=-30),
                    updated_at=stamp(hours=-30)),
        ], seq=4)
        self.write("demo@fleetglint", [
            run("demo-1", source_id="demo@fleetglint", title="demo run",
                updated_at=stamp(seconds=-60), observed_at=stamp(seconds=-60)),
        ])
        self.ing.scan_roots()
        self.backend = query.QueryBackend(self.cfg)

    @staticmethod
    def disable_adapters(cfg):
        for adapter in (cfg.harness, cfg.claude_code, cfg.codex):
            adapter.enabled = "false"

    def write(self, source_id, records, seq=None):
        directory = self.root / source_id
        directory.mkdir(parents=True, exist_ok=True)
        if seq is None:
            # Segments must be contiguous (spec §7.4), so continue after the last one.
            existing = [int(path.name[:10]) for path in directory.iterdir()
                        if path.name[:10].isdigit()
                        and path.name.endswith((".ndjson", ".ndjson.gz"))]
            seq = max(existing, default=0) + 1
        path = directory / f"{seq:010d}.ndjson"
        path.write_text("".join(json.dumps(record) + "\n" for record in records),
                        encoding="utf-8")
        return path

    def snapshot(self, backend=None):
        return (backend or self.backend).snapshot(NOW)

    def by_id(self, items):
        return {item["ref"]["id"]: item for item in items}

    # --- snapshot shape ---------------------------------------------------

    def test_snapshot_shape_and_lists(self):
        snap = self.snapshot()
        self.assertEqual(keys(snap), SNAPSHOT_KEYS)
        self.assertEqual(snap["api"], 1)
        self.assertEqual(snap["generated_at"], NOW.isoformat())
        self.assertEqual(snap["window_hours"], 24)
        self.assertEqual(keys(snap["server"]), {"version", "host", "read_only"})
        self.assertTrue(snap["server"]["read_only"])
        self.assertEqual(keys(snap["counts"]),
                         {"running", "waiting", "attention", "stale_lost_unknown",
                          "sessions_recent"})
        self.assertEqual(keys(snap["truncated"]), {"runs", "jobs", "inbox", "sessions"})
        self.assertTrue(snap["demo"])

        for item in snap["runs"]:
            self.assertEqual(keys(item), RUN_KEYS)
            self.assertEqual(keys(item["ref"]), REF_KEYS)
            self.assertEqual(keys(item["evidence"]), EVIDENCE_KEYS)
        for item in snap["jobs"]:
            self.assertEqual(keys(item), JOB_KEYS)
        for item in snap["inbox"]:
            self.assertEqual(keys(item), INBOX_KEYS)
        for item in snap["sessions"]:
            self.assertEqual(keys(item), SESSION_KEYS)
        for entry in snap["attention"]:
            self.assertEqual(keys(entry), ATTENTION_KEYS)
        for source in snap["sources"]:
            self.assertEqual(keys(source), {"source_id", "kind", "status", "detail",
                                            "last_scan_at", "last_record_at",
                                            "quarantine_count", "records"})

        runs = self.by_id(snap["runs"])
        self.assertEqual(set(runs), {"lead-1", "w-1", "waiting-1", "resumed-1", "stale-1",
                                     "unknown-1", "done-1", "demo-1"})
        self.assertNotIn("old-done", runs)  # terminal outside the 24 h window
        self.assertEqual(set(self.by_id(snap["jobs"])), {"j-1", "j-done"})
        self.assertNotIn("j-old", self.by_id(snap["jobs"]))
        self.assertEqual(set(self.by_id(snap["inbox"])), {"i-action", "i-open", "i-acked"})
        self.assertEqual(set(self.by_id(snap["sessions"])),
                         {"sess-recent", "sess-child", "sess-idle", "sess-ended"})

    def test_display_states_and_counts(self):
        snap = self.snapshot()
        runs = self.by_id(snap["runs"])
        jobs = self.by_id(snap["jobs"])
        sessions = self.by_id(snap["sessions"])

        self.assertEqual(runs["w-1"]["state"], "running")
        self.assertEqual(runs["w-1"]["display_state"], "running")
        self.assertEqual(runs["w-1"]["evidence"],
                         {"kind": "observed", "age_s": 10, "detail": None})
        self.assertEqual(runs["stale-1"]["display_state"], "stale")
        self.assertEqual(runs["stale-1"]["evidence"]["kind"], "expired")
        self.assertEqual(runs["stale-1"]["evidence"]["age_s"], 42 * 60)
        self.assertEqual(runs["unknown-1"]["display_state"], "unknown")
        self.assertEqual(runs["unknown-1"]["evidence"]["kind"], "writer_unknown")
        self.assertEqual(runs["done-1"]["display_state"], "done")
        self.assertEqual(runs["done-1"]["evidence"], {"kind": "terminal", "age_s": None,
                                                      "detail": None})
        self.assertEqual(runs["waiting-1"]["display_state"], "waiting")
        self.assertEqual(jobs["j-1"]["display_state"], "running")
        self.assertEqual(sessions["sess-recent"]["display_state"], "recent")
        self.assertEqual(sessions["sess-recent"]["evidence"]["kind"], "activity")
        self.assertEqual(sessions["sess-idle"]["display_state"], "idle")
        self.assertEqual(sessions["sess-ended"]["display_state"], "ended")
        self.assertEqual(sessions["sess-ended"]["evidence"]["kind"], "terminal")

        self.assertEqual(snap["counts"], {
            "running": 4,     # lead-1, w-1, demo-1, j-1
            "waiting": 2,     # waiting-1, resumed-1
            "attention": 4,   # i-action, i-open, stale-1, unknown-1
            "stale_lost_unknown": 2,  # stale-1, unknown-1
            "sessions_recent": 2,     # sess-recent, sess-child
        })
        self.assertEqual(snap["counts"]["attention"], len(snap["attention"]))

    def test_ordering_is_newest_first(self):
        snap = self.snapshot()
        for name, field in (("runs", "updated_at"), ("jobs", "updated_at"),
                            ("inbox", "updated_at"), ("sessions", "observed_at")):
            values = [item[field] for item in snap[name]]
            self.assertEqual(values, sorted(values, reverse=True), name)
        self.assertEqual([item["ref"]["id"] for item in snap["runs"]][:3],
                         ["resumed-1", "waiting-1", "w-1"])
        self.assertEqual([item["ref"]["id"] for item in snap["inbox"]],
                         ["i-acked", "i-open", "i-action"])
        self.assertEqual([item["ref"]["id"] for item in snap["sessions"]],
                         ["sess-recent", "sess-child", "sess-idle", "sess-ended"])

    def test_titles_links_and_extended_refs(self):
        snap = self.snapshot()
        runs = self.by_id(snap["runs"])
        jobs = self.by_id(snap["jobs"])
        inbox = self.by_id(snap["inbox"])

        self.assertEqual(runs["w-1"]["title"], "worker task")
        self.assertEqual(runs["w-1"]["links"],
                         [{"label": "log", "path": str(self.log_path), "readable": True}])
        parent = runs["w-1"]["parent_run"]
        self.assertEqual(parent, {"type": "run", "id": "lead-1", "source_id": "work@mbp",
                                  "resolved": True, "display_state": "running",
                                  "title": "lead session"})
        self.assertEqual(runs["w-1"]["resume_of"], None)
        self.assertEqual(runs["resumed-1"]["resume_of"],
                         {"type": "run", "id": "lead-1", "source_id": "work@mbp",
                          "resolved": True, "display_state": "running",
                          "title": "lead session"})
        self.assertEqual(runs["resumed-1"]["waits_on"], [
            {"type": "external", "kind": "github_pr", "key": "owner/repo#1",
             "url": "https://github.com/owner/repo/pull/1"},
            {"type": "run", "id": "w-1", "source_id": "work@mbp", "resolved": True,
             "display_state": "running", "title": "worker task"},
        ])
        self.assertEqual(jobs["j-1"]["run"],
                         {"type": "run", "id": "lead-1", "source_id": "work@mbp",
                          "resolved": True, "display_state": "running",
                          "title": "lead session"})
        self.assertEqual(jobs["j-1"]["log"],
                         {"path": str(self.log_path), "readable": True})
        self.assertIsNone(jobs["j-1"]["result"])
        self.assertEqual(inbox["i-acked"]["subject"],
                         {"type": "external", "kind": "url",
                          "url": "https://example.com/1"})

    def test_unresolved_refs(self):
        self.write("work@mbp", [
            run("r-ghost", parent_run={"type": "run", "id": "missing"}),
        ])
        self.ing.scan_roots()
        item = self.by_id(self.snapshot()["runs"])["r-ghost"]
        self.assertEqual(item["parent_run"],
                         {"type": "run", "id": "missing", "source_id": "work@mbp",
                          "resolved": False})

    def test_attention_order_and_who(self):
        snap = self.snapshot()
        self.assertEqual([(entry["reason"], entry["source_id"])
                          for entry in snap["attention"]],
                         [("action_required", "work@mbp"), ("inbox", "work@mbp"),
                          ("stale", "work@mbp"), ("unknown", "work@mbp")])
        action, notice, stale, unknown = snap["attention"]
        self.assertEqual(action["who"], "lead")
        self.assertEqual(action["subject"],
                         {"type": "job", "id": "j-1", "source_id": "work@mbp",
                          "resolved": True, "display_state": "running",
                          "title": None})
        self.assertIn("job_finished", action["text"])
        self.assertIn("done", action["text"])
        self.assertEqual(notice["who"], "worker")
        self.assertEqual(notice["subject"]["id"], "w-1")
        self.assertEqual(stale["who"], "lead")
        self.assertEqual(stale["subject"],
                         {"type": "run", "id": "stale-1", "source_id": "work@mbp",
                          "resolved": True, "display_state": "stale",
                          "title": "stale worker"})
        self.assertIn("42m", stale["text"])
        self.assertEqual(unknown["subject"]["id"], "unknown-1")

    def test_attention_skips_lost_stale_unknown_older_than_the_window(self):
        self.write("work@mbp", [
            run("old-stale", updated_at=stamp(hours=-30), observed_at=stamp(hours=-30)),
            run("old-unknown", state="unknown", updated_at=stamp(hours=-30)),
        ])
        self.ing.scan_roots()
        snap = self.snapshot()
        reasons = {(entry["reason"], (entry["subject"] or {}).get("id"))
                   for entry in snap["attention"]}
        self.assertNotIn(("stale", "old-stale"), reasons)
        self.assertNotIn(("unknown", "old-unknown"), reasons)
        self.assertEqual(snap["counts"]["stale_lost_unknown"], 2)  # stale-1, unknown-1 only
        self.assertEqual(snap["counts"]["attention"], 4)

    def test_source_entries(self):
        snap = self.snapshot()
        sources = {source["source_id"]: source for source in snap["sources"]}
        self.assertEqual(set(sources), {"work@mbp", "demo@fleetglint"})
        work = sources["work@mbp"]
        self.assertEqual((work["kind"], work["status"], work["detail"]),
                         ("ndjson", "ok", None))
        self.assertEqual(work["last_scan_at"], NOW.isoformat())
        self.assertIsNotNone(work["last_record_at"])
        self.assertEqual(work["quarantine_count"], 0)
        self.assertGreater(work["records"], 0)

    def test_list_limit_sets_truncated(self):
        self.backend.list_limit = 2
        snap = self.snapshot()
        self.assertEqual(len(snap["runs"]), 2)
        self.assertEqual(len(snap["inbox"]), 2)
        self.assertEqual(len(snap["sessions"]), 2)
        self.assertEqual(snap["truncated"],
                         {"runs": True, "jobs": False, "inbox": True, "sessions": True})
        self.assertEqual([item["ref"]["id"] for item in snap["runs"]],
                         ["resumed-1", "waiting-1"])

    def test_attention_and_counts_use_rows_beyond_the_list_limit(self):
        self.backend.list_limit = 1
        snap = self.snapshot()
        self.assertTrue(snap["truncated"]["inbox"])
        self.assertEqual([item["ref"]["id"] for item in snap["inbox"]], ["i-acked"])
        # The old action_required item is behind newer inbox rows but still leads attention.
        self.assertEqual(len(snap["attention"]), 1)
        action = snap["attention"][0]
        self.assertEqual(action["reason"], "action_required")
        self.assertEqual(action["subject"]["id"], "j-1")
        self.assertIn("review the PR", action["text"])
        self.assertEqual(snap["counts"]["attention"], 4)
        self.assertEqual(snap["counts"]["running"], 4)
        self.assertEqual(snap["counts"]["sessions_recent"], 2)

    def test_demo_flag_only_for_demo_sources(self):
        snap = self.snapshot()
        self.assertTrue(snap["demo"])
        # A board without any demo@ record is not a demo board.
        self.conn.execute("DELETE FROM records WHERE source_id LIKE 'demo@%'")
        self.conn.commit()
        self.assertFalse(self.snapshot()["demo"])
        # Every demo@ source is demo data, not only the built-in one (architecture §8.1).
        self.write("demo@host", [run("demo-2", source_id="demo@host")])
        self.ing.scan_roots()
        self.assertTrue(self.snapshot()["demo"])

    # --- record -----------------------------------------------------------

    def test_record_shape_full_history_and_usage(self):
        data = self.backend.record(NOW, "work@mbp", "run", "lead-1")
        self.assertEqual(keys(data), RECORD_KEYS)
        self.assertEqual(keys(data["record"]), RUN_KEYS)
        self.assertEqual(data["record"]["ref"],
                         {"type": "run", "id": "lead-1", "source_id": "work@mbp"})
        self.assertEqual(data["full"]["id"], "lead-1")
        self.assertEqual(data["full"]["title"], "lead session")
        self.assertEqual(data["full"]["summary"], "lead summary")
        self.assertEqual(data["full"]["usage"], {"basis": "measured", "input_tokens": 10})
        self.assertEqual(data["usage"], {"basis": "measured", "input_tokens": 10})
        self.assertEqual(keys(data["relations"]), RELATION_KEYS)
        self.assertEqual(data["relations"]["parent"], None)
        self.assertEqual(data["relations"]["resume_of"], None)
        self.assertEqual([ref["id"] for ref in data["relations"]["children"]], ["w-1"])
        self.assertEqual(data["relations"]["children"][0]["resolved"], True)
        self.assertEqual([ref["id"] for ref in data["relations"]["resumed_by"]],
                         ["resumed-1"])
        self.assertEqual(sorted(ref["id"] for ref in data["relations"]["jobs"]),
                         ["j-1", "j-done"])
        self.assertEqual([ref["id"] for ref in data["relations"]["inbox"]], [])
        self.assertEqual(data["relations"]["waited_on_by"], [])
        self.assertEqual(len(data["history"]), 1)
        self.assertEqual(keys(data["history"][0]),
                         {"seq", "byte_offset", "updated_at", "state"})
        self.assertEqual((data["history"][0]["seq"], data["history"][0]["updated_at"],
                          data["history"][0]["state"]), (1, stamp(seconds=-90), "running"))

    def test_record_relations_both_ways(self):
        child = self.backend.record(NOW, "work@mbp", "run", "w-1")
        self.assertEqual(child["relations"]["parent"]["id"], "lead-1")
        self.assertEqual([ref["id"] for ref in child["relations"]["waited_on_by"]],
                         ["resumed-1"])
        self.assertEqual([ref["id"] for ref in child["relations"]["inbox"]], ["i-open"])
        self.assertEqual(child["history"][0]["updated_at"], stamp(seconds=-30))
        self.assertEqual(child["history"][1]["updated_at"], stamp(seconds=-40))
        self.assertEqual([entry["state"] for entry in child["history"]],
                         ["running", "running"])

    def test_job_record(self):
        data = self.backend.record(NOW, "work@mbp", "job", "j-1")
        self.assertEqual(keys(data["record"]), JOB_KEYS)
        self.assertEqual(data["record"]["run"]["id"], "lead-1")
        self.assertEqual(data["relations"]["parent"], None)
        self.assertEqual(data["relations"]["children"], [])
        self.assertEqual(data["relations"]["resumed_by"], [])
        self.assertEqual(data["relations"]["jobs"], [])
        self.assertEqual([ref["id"] for ref in data["relations"]["inbox"]], ["i-action"])
        self.assertIsNone(data["usage"])

    def test_inbox_record(self):
        data = self.backend.record(NOW, "work@mbp", "inbox_item", "i-action")
        self.assertEqual(keys(data["record"]), INBOX_KEYS)
        self.assertEqual(data["record"]["subject"]["id"], "j-1")
        self.assertTrue(data["record"]["action_required"])
        self.assertIsInstance(data["record"]["blocks_retention"], bool)
        self.assertEqual(data["relations"]["inbox"], [])

    def test_history_is_capped_at_fifty_newest_first(self):
        # Written oldest first, as a real writer appends them.
        records = [run("busy", updated_at=stamp(minutes=-(59 - index)))
                   for index in range(60)]
        self.write("work@mbp", records)
        self.ing.scan_roots()
        data = self.backend.record(NOW, "work@mbp", "run", "busy")
        self.assertEqual(len(data["history"]), 50)
        self.assertEqual(data["history"][0]["updated_at"], stamp(minutes=0))
        self.assertEqual(data["history"][-1]["updated_at"], stamp(minutes=-49))
        self.assertEqual([entry["updated_at"] for entry in data["history"]],
                         sorted((entry["updated_at"] for entry in data["history"]),
                                reverse=True))

    def test_record_with_meanwhile_deleted_source_rows(self):
        self.assertEqual(self.backend.record(NOW, "work@mbp", "run", "missing"), None)
        self.assertEqual(self.backend.record(NOW, "nope@x", "run", "lead-1"), None)

    # --- file -------------------------------------------------------------

    def test_file_reads_and_redacts_the_tail(self):
        data = self.backend.file(NOW, "work@mbp", "job", "j-1", "log_path", None)
        self.assertEqual(keys(data), {"api", "readable", "path", "size", "truncated",
                                      "text", "redactions"})
        self.assertEqual(data["api"], 1)
        self.assertTrue(data["readable"])
        self.assertEqual(data["path"], str(self.log_path.resolve()))
        self.assertEqual(data["size"], self.log_path.stat().st_size)
        self.assertFalse(data["truncated"])
        self.assertIn("[redacted]", data["text"])
        self.assertNotIn(SECRET, data["text"])
        self.assertEqual(data["redactions"], 1)

    def test_file_link_index(self):
        data = self.backend.file(NOW, "work@mbp", "run", "w-1", "link", 0)
        self.assertTrue(data["readable"])
        self.assertEqual(data["path"], str(self.log_path.resolve()))
        self.assertEqual(self.backend.file(NOW, "work@mbp", "run", "w-1", "link", 5),
                         {"api": 1, "readable": False, "reason": "no_path"})
        self.assertEqual(self.backend.file(NOW, "work@mbp", "run", "w-1", "link", None),
                         {"api": 1, "readable": False, "reason": "no_path"})

    def test_file_outside_allowed_roots_and_missing(self):
        self.write("work@mbp", [
            job("j-out", log_path=str(self.outside_path)),
            job("j-missing", log_path=str(self.root / "work@mbp" / "nope.log")),
            job("j-nopath"),
        ])
        self.ing.scan_roots()
        outside = self.backend.file(NOW, "work@mbp", "job", "j-out", "log_path", None)
        self.assertEqual(outside, {"api": 1, "readable": False,
                                   "reason": "outside_allowed_roots"})
        missing = self.backend.file(NOW, "work@mbp", "job", "j-missing", "log_path", None)
        self.assertEqual(missing["readable"], False)
        self.assertEqual(missing["reason"], "missing")
        nopath = self.backend.file(NOW, "work@mbp", "job", "j-nopath", "log_path", None)
        self.assertEqual(nopath, {"api": 1, "readable": False, "reason": "no_path"})
        self.assertIsNone(self.backend.file(NOW, "work@mbp", "job", "nope",
                                            "log_path", None))

    # --- quarantine -------------------------------------------------------

    def test_quarantine_redacts_excerpts(self):
        good = json.dumps(run("bad-ok", source_id="bad@mbp"))
        bad = '{"v":1,"note":"' + SECRET + '" broken'
        segment = self.write("bad@mbp", [], seq=1)
        segment.write_text(good + "\n" + bad + "\n", encoding="utf-8")
        self.write("bad@mbp", [run("bad-ok", state="running", source_id="bad@mbp")], seq=2)
        self.ing.scan_roots()

        lines = self.backend.quarantine("bad@mbp")
        self.assertEqual(len(lines), 1)
        self.assertEqual(keys(lines[0]), {"position", "reason", "excerpt"})
        self.assertRegex(lines[0]["position"], r"^\d{10}:\d+$")
        self.assertTrue(lines[0]["position"].startswith("0000000001:"))
        self.assertEqual(lines[0]["reason"], "invalid_json")
        self.assertIn("[redacted]", lines[0]["excerpt"])
        self.assertNotIn(SECRET, lines[0]["excerpt"])
        self.assertIsNone(self.backend.quarantine("nope@x"))

    # --- empty board ------------------------------------------------------

    def test_empty_board_when_the_database_is_missing(self):
        cfg = config.Config()
        cfg.db_path = self.dir / "no-such-dir" / "empty.sqlite"
        backend = query.QueryBackend(cfg)
        self.assertEqual(backend.change_counter(), 0)
        snap = backend.snapshot(NOW)
        self.assertEqual(keys(snap), SNAPSHOT_KEYS)
        self.assertEqual(snap, {
            "api": 1,
            "generated_at": NOW.isoformat(),
            "server": snap["server"],
            "window_hours": 24,
            "sources": [],
            "counts": {"running": 0, "waiting": 0, "attention": 0,
                       "stale_lost_unknown": 0, "sessions_recent": 0},
            "runs": [], "jobs": [], "inbox": [], "sessions": [], "attention": [],
            "truncated": {"runs": False, "jobs": False, "inbox": False, "sessions": False},
            "demo": False,
        })
        self.assertIsNone(backend.record(NOW, "work@mbp", "run", "lead-1"))
        self.assertIsNone(backend.file(NOW, "work@mbp", "run", "lead-1", "log_path", None))
        self.assertIsNone(backend.quarantine("work@mbp"))

    def test_change_counter_moves_with_ingestion(self):
        before = self.backend.change_counter()
        self.write("work@mbp", [run("counter-1", updated_at=stamp(seconds=-1))])
        self.ing.scan_roots()
        self.assertGreater(self.backend.change_counter(), before)


class BoardTest(unittest.TestCase):
    """GET /api/board: one place per record, in the documented order (architecture §4.1b)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.root = self.dir / "sources"
        self.root.mkdir()
        cfg = config.Config()
        cfg.roots = [self.root]
        cfg.db_path = self.dir / "db.sqlite"
        for adapter in (cfg.harness, cfg.claude_code, cfg.codex):
            adapter.enabled = "false"
        self.cfg = cfg
        self.conn = store.open_db(cfg.db_path)
        self.addCleanup(self.conn.close)
        self.ing = ingest.Ingestor(self.conn, cfg, clock=lambda: NOW)
        self.backend = query.QueryBackend(cfg)

    def write(self, records, source_id="work@mbp"):
        directory = self.root / source_id
        directory.mkdir(parents=True, exist_ok=True)
        existing = [int(path.name[:10]) for path in directory.iterdir()
                    if path.name[:10].isdigit()
                    and path.name.endswith((".ndjson", ".ndjson.gz"))]
        path = directory / f"{max(existing, default=0) + 1:010d}.ndjson"
        path.write_text("".join(json.dumps(record) + "\n" for record in records),
                        encoding="utf-8")
        self.ing.scan_roots()
        return path

    def put_raw(self, record):
        """Store a row the schema would reject, for cases ingest cannot produce."""
        store.put_latest(self.conn, record, 900, 0)
        self.conn.commit()

    def board(self, backend=None):
        return (backend or self.backend).board(NOW)

    def by_id(self, items):
        return {item["ref"]["id"]: item for item in items}

    # --- shape ------------------------------------------------------------

    def test_board_prefers_latest_scanned_source(self):
        self.write([job("shared", source_id="harness@old", project="scratchpad",
                        observed_at=stamp())], source_id="harness@old")
        self.write([job("shared", source_id="harness@new", state="done", project="gteki",
                        observed_at=stamp(minutes=-1), ended_at=stamp())],
                   source_id="harness@new")
        self.conn.execute("UPDATE sources SET kind = 'adapter'")
        self.conn.execute("UPDATE sources SET last_scan_at = ? WHERE source_id = ?",
                          (stamp(days=-3), "harness@old"))
        self.conn.commit()

        board = self.board()
        self.assertEqual(board["running"], [])
        self.assertEqual(board["counts"]["running"], 0)
        self.assertEqual([item["ref"]["source_id"] for item in board["recent"]],
                         ["harness@new"])
        self.assertEqual([p["project"] for p in board["projects"]], ["gteki"])

    def test_board_keeps_different_adapters_and_record_types(self):
        for source_id in ("claude-code@h", "codex-cli@h"):
            self.write([job("shared", source_id=source_id)], source_id=source_id)
        self.write([run("shared", source_id="claude-code@h")], source_id="claude-code@h")
        self.conn.execute("UPDATE sources SET kind = 'adapter'")
        self.conn.commit()

        board = self.board()
        self.assertEqual({(item["ref"]["source_id"], item["ref"]["type"])
                          for item in board["running"]},
                         {("claude-code@h", "job"), ("codex-cli@h", "job"),
                          ("claude-code@h", "run")})
        self.assertEqual(board["counts"]["running"], 3)

    def test_board_keeps_records_unique_to_old_source(self):
        self.write([job("old-only", source_id="harness@old")], source_id="harness@old")
        self.write([job("new-only", source_id="harness@new")], source_id="harness@new")
        self.conn.execute("UPDATE sources SET kind = 'adapter'")
        self.conn.execute("UPDATE sources SET last_scan_at = ? WHERE source_id = ?",
                          (stamp(days=-3), "harness@old"))
        self.conn.commit()

        board = self.board()
        self.assertEqual(set(self.by_id(board["running"])), {"old-only", "new-only"})
        self.assertEqual(board["counts"]["running"], 2)

    def test_board_source_scan_ties_and_missing_values(self):
        self.write([job("shared", source_id="harness@old", observed_at=stamp())],
                   source_id="harness@old")
        self.write([job("shared", source_id="harness@new", observed_at=stamp(minutes=-1))],
                   source_id="harness@new")
        for old_scan, new_scan, expected in (
                (stamp(), stamp(), "harness@old"),
                (None, stamp(), "harness@new"),
                (stamp(), None, "harness@old"),
                (None, None, "harness@old")):
            with self.subTest(old_scan=old_scan, new_scan=new_scan):
                self.conn.executemany("UPDATE sources SET kind = 'adapter', last_scan_at = ? WHERE source_id = ?",
                                      [(old_scan, "harness@old"), (new_scan, "harness@new")])
                self.conn.commit()
                self.assertEqual([item["ref"]["source_id"]
                                  for item in self.board()["running"]], [expected])

    def test_board_deduplicates_sessions_before_window_filter(self):
        self.write([session("shared", source_id="claude-code@old", observed_at=stamp())],
                   source_id="claude-code@old")
        self.write([session("shared", source_id="claude-code@new",
                            observed_at=stamp(hours=-30), last_activity_at=stamp(hours=-30),
                            updated_at=stamp(hours=-30))], source_id="claude-code@new")
        self.conn.execute("UPDATE sources SET kind = 'adapter'")
        self.conn.execute("UPDATE sources SET last_scan_at = ? WHERE source_id = ?",
                          (stamp(days=-3), "claude-code@old"))
        self.conn.commit()

        board = self.board()
        self.assertEqual(board["sessions"], [])
        self.assertEqual(board["sessions_total"], 0)
        self.assertEqual(board["counts"]["sessions_recent"], 0)

    def test_board_keeps_ndjson_sources_with_hostname_like_suffixes(self):
        for source_id in ("my-workflow@old", "my-workflow@new"):
            self.write([job("build", source_id=source_id)], source_id=source_id)
        self.conn.execute("UPDATE sources SET last_scan_at = ? WHERE source_id = ?",
                          (stamp(days=-3), "my-workflow@new"))
        self.conn.commit()

        board = self.board()
        self.assertEqual({item["ref"]["source_id"] for item in board["running"]},
                         {"my-workflow@old", "my-workflow@new"})
        self.assertEqual(board["counts"]["running"], 2)

    def test_board_keeps_ndjson_sources_with_and_without_at_sign(self):
        for source_id, project in (("my-workflow", "alpha"), ("my-workflow@local", "beta")):
            self.write([job("build", source_id=source_id, project=project)], source_id=source_id)

        board = self.board()
        self.assertEqual({item["ref"]["source_id"] for item in board["running"]},
                         {"my-workflow", "my-workflow@local"})
        self.assertEqual({p["project"] for p in board["projects"]}, {"alpha", "beta"})
        self.assertEqual(board["counts"]["running"], 2)

    def test_project_board_groups_waiting_job_and_recent_decisions(self):
        self.write([
            run("waiting-run", state="waiting", project="alpha", waits_on=[{"type": "job", "id": "job1"}]),
            job("job1", project="alpha"),
            job("gha-done", state="done", project="alpha", kind="github-actions", ended_at=stamp()),
            job("gha.o.alpha.poll", state="done", project="alpha", kind="github-actions", command_summary="ci-watch poll", ended_at=stamp()),
            run("failed", state="failed", project="beta", summary="broken", ended_at=stamp()),
            {"v": 1, "type": "decision", "id": "new", "source_id": "work@mbp", "updated_at": stamp(), "role_id": "alpha-lead", "project": "alpha", "text": "ship", "decided_at": stamp()},
            {"v": 1, "type": "decision", "id": "old", "source_id": "work@mbp", "updated_at": stamp(days=-8), "role_id": "alpha-lead", "project": "alpha", "text": "old", "decided_at": stamp(days=-8)},
        ])
        projects = self.board()["projects"]
        self.assertEqual(projects[0]["project"], "beta")
        alpha = next(p for p in projects if p["project"] == "alpha")
        self.assertEqual([i["ref"]["id"] for i in alpha["in_progress"]], ["waiting-run"])
        self.assertEqual(alpha["in_progress"][0]["jobs"][0]["ref"]["id"], "job1")
        self.assertEqual([d["ref"]["id"] for d in alpha["decisions"]], ["new"])
        self.assertEqual(set(self.by_id(alpha["recent"]["done"])), {"gha-done"})
        self.assertEqual(alpha["needs_you"], [])
        self.assertEqual(projects[0]["needs_you"][0]["section_reason"], "broken")

    def test_project_ci_poll_recovery_clears_needs_you(self):
        self.write([job("gha.o.alpha.poll", state="unknown", project="alpha", kind="github-actions",
                        command_summary="ci-watch poll", updated_at=stamp(hours=-1), observed_at=stamp(hours=-1))])
        alpha = next(p for p in self.board()["projects"] if p["project"] == "alpha")
        self.assertEqual(set(self.by_id(alpha["needs_you"])), {"gha.o.alpha.poll"})
        self.write([job("gha.o.alpha.poll", state="done", project="alpha", kind="github-actions",
                        command_summary="ci-watch poll", ended_at=stamp())])
        alpha = next(p for p in self.board()["projects"] if p["project"] == "alpha")
        self.assertEqual(alpha["needs_you"], [])
        self.assertEqual(alpha["recent"]["done"], [])

    def test_project_needs_you_ages_out_and_drops_superseded_lines(self):
        self.write([
            job("gha-failed", state="failed", project="alpha", kind="github-actions", command_summary="CI · main · push", updated_at=stamp(hours=-2), ended_at=stamp(hours=-2)),
            job("gha-done", state="done", project="alpha", kind="github-actions", command_summary="CI · main · push", updated_at=stamp(hours=-1), ended_at=stamp(hours=-1)),
            job("gha-earlier", state="done", project="alpha", kind="github-actions", command_summary="CI · dev · push", updated_at=stamp(hours=-2), ended_at=stamp(hours=-2)),
            job("gha-later-failure", state="failed", project="alpha", kind="github-actions", command_summary="CI · dev · push", updated_at=stamp(hours=-1), ended_at=stamp(hours=-1)),
            job("job-failed", state="failed", project="alpha", cwd="/work/a", updated_at=stamp(hours=-2), ended_at=stamp(hours=-2)),
            job("job-other-role", state="failed", project="alpha", cwd="/work/b", updated_at=stamp(hours=-2), ended_at=stamp(hours=-2)),
            job("job-done", state="done", project="alpha", cwd="/work/a", updated_at=stamp(hours=-1), ended_at=stamp(hours=-1)),
            job("cwd-role-a", state="failed", project="alpha", cwd="/work/c", kind="wait-worker", role_id="a-lead", title="task-a", command_summary="cwd-worker", updated_at=stamp(hours=-2), ended_at=stamp(hours=-2)),
            job("cwd-role-b", state="done", project="alpha", cwd="/work/c", kind="wait-worker", role_id="b-lead", title="task-b", updated_at=stamp(hours=-1), ended_at=stamp(hours=-1)),
            job("wait-failed", state="failed", project="alpha", kind="wait-worker", role_id="worker", title="first", updated_at=stamp(hours=-2), ended_at=stamp(hours=-2)),
            job("wait-other", state="failed", project="alpha", kind="wait-worker", role_id="worker", title="other", updated_at=stamp(hours=-2), ended_at=stamp(hours=-2)),
            job("wait-done", state="done", project="alpha", kind="wait-worker", role_id="worker", title="first", updated_at=stamp(hours=-1), ended_at=stamp(hours=-1)),
            run("run-failed", state="failed", project="alpha", title="same", updated_at=stamp(hours=-2), ended_at=stamp(hours=-2)),
            run("run-done", state="done", project="alpha", title="same", updated_at=stamp(hours=-1), ended_at=stamp(hours=-1)),
            job("old-lost", project="alpha", command_summary="old", process={"host": "mbp", "pid": 424242}, updated_at=stamp(hours=-25)),
            job("new-lost", project="alpha", command_summary="new", process={"host": "mbp", "pid": 424242}, updated_at=stamp(hours=-1)),
        ])

        class Dead:
            def check(self, process):
                return False

        alpha = next(p for p in self.board(query.QueryBackend(self.cfg, process_checker=Dead()))["projects"] if p["project"] == "alpha")
        self.assertEqual(set(self.by_id(alpha["needs_you"])), {"gha-later-failure", "job-other-role", "cwd-role-a", "wait-other", "run-failed", "new-lost"})
        self.assertEqual(alpha["needs_you_total"], 6)
        self.assertIn("gha-failed", self.by_id(alpha["recent"]["failed"]))
        self.assertIn("job-failed", self.by_id(alpha["recent"]["failed"]))

    def test_project_unknown_oracle_dot_ci_stays_only_in_global_exceptions(self):
        self.write([
            run("dot-ci-title", state="unknown", project="alpha", agent="oracle", title="dot-ci"),
            run("dot-ci-worker", state="unknown", project="alpha", agent="oracle", title="review", worker="dot-ci"),
            run("cx", state="unknown", project="alpha", agent="cx", title="dot-ci"),
            run("oracle-other", state="unknown", project="alpha", agent="oracle", title="review"),
        ])
        board = self.board()
        alpha = next(p for p in board["projects"] if p["project"] == "alpha")
        self.assertEqual(set(self.by_id(alpha["needs_you"])), {"cx", "oracle-other"})
        self.assertEqual(set(self.by_id(board["exceptions"]["unverified_recent"])),
                         {"dot-ci-title", "dot-ci-worker", "cx", "oracle-other"})

    def test_project_gha_failure_superseded_by_any_newer_state(self):
        for state in ("running", "queued", "unknown", "failed", "done"):
            with self.subTest(state=state):
                project = f"alpha-{state}"
                self.write([
                    job(f"old-{state}", state="failed", project=project, kind="github-actions",
                        command_summary="CI · main · push", exit_code=1,
                        updated_at=stamp(hours=-2), ended_at=stamp(hours=-2)),
                    job(f"new-{state}", state=state, project=project, kind="github-actions",
                        command_summary="CI · main · push", exit_code=2 if state == "failed" else None,
                        updated_at=stamp(minutes=-1), observed_at=stamp(minutes=-1),
                        **({"ended_at": stamp(minutes=-1)} if state in ("failed", "done") else {})),
                ])
                card = next(p for p in self.board()["projects"] if p["project"] == project)
                expected = {f"new-{state}"} if state in ("unknown", "failed") else set()
                self.assertEqual(set(self.by_id(card["needs_you"])), expected)

    def test_project_gha_new_failure_and_separate_branches(self):
        self.write([
            job("done-main", state="done", project="alpha", kind="github-actions",
                command_summary="CI · main · push", updated_at=stamp(hours=-2), ended_at=stamp(hours=-2)),
            job("failed-main", state="failed", project="alpha", kind="github-actions",
                command_summary="CI · main · push", exit_code=1,
                updated_at=stamp(hours=-1), ended_at=stamp(hours=-1)),
            job("failed-dev", state="failed", project="alpha", kind="github-actions",
                command_summary="CI · dev · push", exit_code=2, ended_at=stamp()),
        ])
        alpha = next(p for p in self.board()["projects"] if p["project"] == "alpha")
        # Different exits keep these as separate failure classes when repeats collapse.
        self.assertEqual(set(self.by_id(alpha["needs_you"])), {"failed-main", "failed-dev"})

    def test_project_gha_failures_on_different_branches_do_not_collapse(self):
        self.write([
            job("main-failed", state="failed", project="alpha", kind="github-actions",
                command_summary="CI · main · push", exit_code=1, updated_at=stamp(hours=-1),
                ended_at=stamp(hours=-1)),
            job("dev-failed", state="failed", project="alpha", kind="github-actions",
                command_summary="CI · dev · push", exit_code=1, ended_at=stamp()),
        ])
        alpha = next(p for p in self.board()["projects"] if p["project"] == "alpha")
        items = self.by_id(alpha["needs_you"])
        self.assertEqual(set(items), {"main-failed", "dev-failed"})
        for item in items.values():
            self.assertNotIn("repeat_count", item)

    def test_project_gha_old_in_progress_and_poll_lines(self):
        self.write([
            job("old-running", project="alpha", kind="github-actions", updated_at=stamp(hours=-26),
                command_summary="CI · main · push"),
            job("recent-failed", state="failed", project="alpha", kind="github-actions",
                command_summary="CI · main · push", ended_at=stamp()),
            job("failed.poll", state="unknown", project="alpha", kind="github-actions",
                command_summary="ci-watch poll", updated_at=stamp(hours=-1)),
            job("other.poll", state="done", project="alpha", kind="github-actions",
                command_summary="ci-watch poll", ended_at=stamp()),
        ])
        alpha = next(p for p in self.board()["projects"] if p["project"] == "alpha")
        self.assertEqual(set(self.by_id(alpha["needs_you"])), {"recent-failed", "failed.poll"})

    def test_project_needs_you_collapses_repeats_before_inbox_and_totals(self):
        self.cfg.viewer_roles = ["owner"]
        self.write([
            job("first", state="failed", project="alpha", command_summary="orb-test -- a",
                exit_code=5, updated_at=stamp(hours=-3), ended_at=stamp(hours=-3)),
            job("different-exit", state="failed", project="alpha", command_summary="orb-test -- a",
                exit_code=1, updated_at=stamp(hours=-2), ended_at=stamp(hours=-2)),
            job("middle", state="failed", project="alpha", command_summary="orb-test -- a",
                exit_code=5, updated_at=stamp(hours=-1), ended_at=stamp(hours=-1)),
            job("newest", state="failed", project="alpha", command_summary="orb-test -- a",
                exit_code=5, ended_at=stamp()),
        ])
        alpha = next(p for p in self.board()["projects"] if p["project"] == "alpha")
        items = self.by_id(alpha["needs_you"])
        self.assertEqual(set(items), {"newest", "different-exit"})
        self.assertEqual(items["newest"]["repeat_count"], 3)
        self.assertNotIn("repeat_count", items["different-exit"])
        self.assertEqual(alpha["needs_you_total"], 2)
        self.assertEqual(len(alpha["recent"]["failed"]), 4)

        self.write([inbox(f"inbox-{i}", project="alpha", role_id="owner", action_required=True,
                          created_at=stamp(minutes=i - 3))
                    for i in (1, 2)])
        board = self.board()
        alpha = next(p for p in board["projects"] if p["project"] == "alpha")
        self.assertEqual(alpha["needs_you_total"], 4)
        self.assertEqual(set(self.by_id(board["needs_you"])), {"inbox-1", "inbox-2"})
        self.assertEqual([item["ref"]["id"] for item in alpha["needs_you"]],
                         ["inbox-2", "inbox-1", "newest", "different-exit"])
        for item in alpha["needs_you"][:2] + board["needs_you"]:
            self.assertNotIn("repeat_count", item)

    def test_project_needs_you_job_repeats_use_full_command(self):
        for project, commands, count in (
                ("distinct", ("sh -c 'a'", "sh -c 'b'"), 2),
                ("identical", ("sh -c 'a'", "sh -c 'a'"), 1)):
            with self.subTest(project=project):
                self.write([
                    job(f"{project}-{i}", state="failed", project=project,
                        command_summary=command, ended_at=stamp())
                    for i, command in enumerate(commands)
                ])
                card = next(p for p in self.board()["projects"] if p["project"] == project)
                self.assertEqual(len(card["needs_you"]), count)
                self.assertEqual(card["needs_you_total"], count)
                for item in card["needs_you"]:
                    if count == 1:
                        self.assertEqual(item["repeat_count"], 2)
                    else:
                        self.assertNotIn("repeat_count", item)

    def test_project_needs_you_job_repeats_use_work_line(self):
        for project, second_cwd, second_role, count in (
                ("different", "/p/web", "frontend-worker", 2),
                ("identical", "/p/api", "backend-worker", 1)):
            with self.subTest(project=project):
                self.write([
                    job(f"{project}-first", state="failed", project=project,
                        command_summary="pnpm test", cwd="/p/api", role_id="backend-worker",
                        updated_at=stamp(hours=-1), ended_at=stamp(hours=-1)),
                    job(f"{project}-second", state="failed", project=project,
                        command_summary="pnpm test", cwd=second_cwd, role_id=second_role,
                        updated_at=stamp(), ended_at=stamp()),
                ])
                card = next(p for p in self.board()["projects"] if p["project"] == project)
                items = self.by_id(card["needs_you"])
                expected = {f"{project}-second"}
                if count == 2:
                    expected.add(f"{project}-first")
                self.assertEqual(set(items), expected)
                self.assertEqual(card["needs_you_total"], count)
                for item in items.values():
                    if count == 1:
                        self.assertEqual(item["repeat_count"], 2)
                        self.assertEqual(set(item), JOB_BOARD_KEYS | {"repeat_count"})
                    else:
                        self.assertNotIn("repeat_count", item)
                        self.assertEqual(set(item), JOB_BOARD_KEYS)

    def test_project_needs_you_job_repeats_fall_back_to_title(self):
        # Ingest requires a command summary; exercise stored records without one.
        for record in [
            job("first", state="failed", project="alpha", command_summary=None,
                title="first task", ended_at=stamp()),
            job("second", state="failed", project="alpha", command_summary=None,
                title="second task", ended_at=stamp()),
            job("second-repeat", state="failed", project="alpha", command_summary=None,
                title="second task", updated_at=stamp(), ended_at=stamp()),
        ]:
            del record["command_summary"]
            self.put_raw(record)
        alpha = next(p for p in self.board()["projects"] if p["project"] == "alpha")
        items = self.by_id(alpha["needs_you"])
        self.assertEqual(set(items), {"first", "second-repeat"})
        self.assertNotIn("repeat_count", items["first"])
        self.assertEqual(items["second-repeat"]["repeat_count"], 2)

    def test_project_needs_you_run_repeats_use_title(self):
        self.write([
            run("foot", state="unknown", project="alpha", title="#1285 (foot)"),
            run("other", state="unknown", project="alpha", title="another task"),
            run("oracle-first", state="failed", project="alpha", agent="oracle",
                title="dot-ci", updated_at=stamp(hours=-1), ended_at=stamp(hours=-1)),
            run("oracle-newest", state="failed", project="alpha", agent="oracle",
                title="dot-ci", updated_at=stamp(), ended_at=stamp()),
        ])
        alpha = next(p for p in self.board()["projects"] if p["project"] == "alpha")
        items = self.by_id(alpha["needs_you"])
        self.assertEqual(set(items), {"foot", "other", "oracle-newest"})
        self.assertEqual(alpha["needs_you_total"], 3)
        for id in ("foot", "other"):
            self.assertNotIn("repeat_count", items[id])
        self.assertEqual(items["oracle-newest"]["repeat_count"], 2)

    def test_project_needs_you_prioritizes_owner_inbox_over_five_failures(self):
        self.cfg.viewer_roles = ["owner"]
        self.write([
            job(f"failure-{i}", state="failed", project="alpha",
                command_summary=f"command-{i}", updated_at=stamp(minutes=-i),
                ended_at=stamp(minutes=-i))
            for i in range(1, 6)
        ] + [inbox("owner-action", project="alpha", role_id="owner", action_required=True,
                   created_at=stamp(hours=-1), updated_at=stamp(hours=-1))])
        board = self.board()
        alpha = next(p for p in board["projects"] if p["project"] == "alpha")
        self.assertEqual(alpha["needs_you"][0]["ref"]["id"], "owner-action")
        self.assertEqual(alpha["needs_you_total"], 6)
        self.assertEqual([item["ref"]["id"] for item in alpha["needs_you"]],
                         ["owner-action"] + [f"failure-{i}" for i in range(1, 6)])
        self.assertEqual([item["ref"]["id"] for item in board["needs_you"]], ["owner-action"])

    def test_project_needs_you_work_is_newest_first_across_runs_and_jobs(self):
        self.write([
            run("older-run", state="failed", project="alpha",
                updated_at=stamp(minutes=-3), ended_at=stamp(minutes=-3)),
            job("newest-job", state="failed", project="alpha", command_summary="build",
                updated_at=stamp(minutes=-1), ended_at=stamp(minutes=-1)),
            job("middle-job", state="failed", project="alpha", command_summary="test",
                updated_at=stamp(minutes=-2), ended_at=stamp(minutes=-2)),
        ])
        alpha = next(p for p in self.board()["projects"] if p["project"] == "alpha")
        self.assertEqual([item["ref"]["id"] for item in alpha["needs_you"]],
                         ["newest-job", "middle-job", "older-run"])

    def test_project_orphan_jobs_unknown_and_global(self):
        self.write([
            run("finished", state="done", project="alpha", ended_at=stamp()),
            job("after-finish", project="alpha", run={"type": "run", "id": "finished"}),
            job("missing-run", project="alpha", run={"type": "run", "id": "missing"}),
            run("unknown", state="unknown", project="alpha"),
            job("unknown-job", state="unknown", project="alpha"),
            run("old-unknown", state="unknown", project="alpha", updated_at=stamp(hours=-26)),
            run("global", state="unknown", role_id="alpha-lead"),
        ])
        projects = {p["project"]: p for p in self.board()["projects"]}
        alpha = projects["alpha"]
        self.assertEqual({i["ref"]["id"] for i in alpha["in_progress"]}, {"after-finish", "missing-run"})
        self.assertEqual({i["ref"]["id"]: i["section_reason"] for i in alpha["needs_you"]},
                         {"unknown": "unverified", "unknown-job": "unverified"})
        self.assertEqual(projects[None]["needs_you"][0]["ref"]["id"], "global")

    def test_board_shape_and_redaction(self):
        self.write([
            run("r1", title=f"hello {SECRET}"),
            job("j1"),
            inbox("i1", role_id="owner", action_required=True),
            session("s1"),
        ])
        board = self.board()
        self.assertEqual(set(board), BOARD_KEYS)
        self.assertEqual(set(board["counts"]), BOARD_COUNT_KEYS)
        self.assertEqual(set(board["truncated"]), BOARD_TRUNCATED_KEYS)
        self.assertEqual(set(board["capabilities"]), {"execution", "requests"})
        self.assertEqual(set(board["exceptions"]),
                         {"process_gone", "out_of_date", "unverified_recent"})
        for item in board["running"]:
            expected = WORK_BOARD_KEYS if item["ref"]["type"] == "run" else JOB_BOARD_KEYS
            self.assertEqual(set(item), expected)
        for item in board["needs_you"]:
            self.assertEqual(set(item), INBOX_BOARD_KEYS)
        for role in board["lead_inbox"]:
            self.assertEqual(set(role), LEAD_INBOX_KEYS)
        self.assertNotIn(SECRET, json.dumps(board))
        self.assertIn("[redacted]", json.dumps(board))
        self.assertFalse(board["demo"])

    def test_capabilities_false_and_true(self):
        self.assertEqual(self.board()["capabilities"],
                         {"execution": False, "requests": False})
        self.write([inbox("i1", role_id="lead", kind="message")])
        self.assertEqual(self.board()["capabilities"],
                         {"execution": False, "requests": True})
        self.write([run("r1")])
        self.assertEqual(self.board()["capabilities"],
                         {"execution": True, "requests": True})

    def test_empty_database_has_the_same_shape(self):
        cfg = config.Config()
        cfg.db_path = self.dir / "no-such-dir" / "empty.sqlite"
        board = query.QueryBackend(cfg).board(NOW)
        self.assertEqual(set(board), BOARD_KEYS)
        self.assertEqual(board["generated_at"], NOW.isoformat())
        self.assertEqual(board["sources"], [])
        self.assertEqual(board["capabilities"], {"execution": False, "requests": False})
        self.assertEqual(board["counts"], dict.fromkeys(BOARD_COUNT_KEYS, 0))
        for name in ("needs_you", "lead_inbox", "waiting", "running", "recent", "sessions"):
            self.assertEqual(board[name], [], name)
        self.assertEqual(board["exceptions"],
                         {"process_gone": [], "out_of_date": [], "unverified_recent": []})
        self.assertEqual(board["truncated"], dict.fromkeys(BOARD_TRUNCATED_KEYS, False))
        self.assertEqual((board["sessions_total"], board["demo"]), (0, False))

    # --- rules ------------------------------------------------------------

    def test_rule1_needs_you_and_24h_age_out(self):
        self.write([
            inbox("i-now", role_id="owner", action_required=True,
                  created_at=stamp(hours=-23)),
            inbox("i-edge", role_id="owner", action_required=True,
                  created_at=stamp(hours=-24)),
            inbox("i-old", role_id="owner", action_required=True,
                  created_at=stamp(hours=-24, seconds=-1)),
            inbox("i-lead", role_id="lead", action_required=True,
                  created_at=stamp(hours=-1)),
        ])
        board = self.board()
        self.assertEqual([item["ref"]["id"] for item in board["needs_you"]],
                         ["i-now", "i-edge"])
        self.assertEqual(board["counts"]["needs_you"], 2)
        self.assertEqual([item["age_s"] for item in board["needs_you"]],
                         [23 * 3600, 24 * 3600])
        # The aged-out viewer item lands nowhere; the non-viewer role goes to lead_inbox.
        self.assertEqual([role["role_id"] for role in board["lead_inbox"]], ["lead"])
        self.assertEqual(board["lead_inbox"][0]["open"], 1)

    def test_rule2_lead_inbox_groups_sorts_and_caps_items(self):
        records = [inbox("lead-old", role_id="lead", kind="message",
                         created_at=stamp(hours=-5), updated_at=stamp(hours=-5))]
        records += [inbox(f"lead-{age}", role_id="lead", kind="message",
                          action_required=(age == 40),
                          created_at=stamp(minutes=-age), updated_at=stamp(minutes=-age))
                    for age in (10, 20, 30, 40, 50, 60)]
        records.append(inbox("worker-1", role_id="worker", kind="message",
                             created_at=stamp(minutes=-5), updated_at=stamp(minutes=-5)))
        self.write(records)
        board = self.board()
        self.assertEqual([role["role_id"] for role in board["lead_inbox"]],
                         ["lead", "worker"])
        lead, worker = board["lead_inbox"]
        self.assertEqual((lead["open"], lead["old"]), (7, 1))
        self.assertEqual(lead["oldest_age_s"], 5 * 3600)
        self.assertEqual(lead["action_required"], 1)
        self.assertEqual([item["ref"]["id"] for item in lead["items"]],
                         ["lead-10", "lead-20", "lead-30", "lead-40", "lead-50"])
        self.assertEqual((worker["open"], worker["old"], worker["action_required"]), (1, 0, 0))
        self.assertEqual((board["counts"]["lead_inbox_open"],
                          board["counts"]["lead_inbox_old"]), (8, 1))
        self.assertTrue(board["truncated"]["lead_inbox"])

    def test_lead_inbox_project_totals_include_truncated_items(self):
        self.write([
            inbox(f"alpha-{age}", role_id="lead", project="alpha",
                  created_at=stamp(hours=-age), action_required=(age == 8))
            for age in range(1, 9)
        ])
        role = self.board()["lead_inbox"][0]
        self.assertEqual(role["open"], 8)
        self.assertEqual(len(role["items"]), 5)
        self.assertEqual(role["by_project"],
                         [{"project": "alpha", "open": 8, "old": 4, "action_required": 1}])
        self.write([
            inbox("beta", role_id="lead", project="beta"),
            inbox("global", role_id="lead"),
        ])
        role = self.board()["lead_inbox"][0]
        self.assertEqual(role["by_project"], [
            {"project": "alpha", "open": 8, "old": 4, "action_required": 1},
            {"project": "beta", "open": 1, "old": 0, "action_required": 0},
            {"project": None, "open": 1, "old": 0, "action_required": 0},
        ])

    def test_lead_inbox_project_name_is_redacted(self):
        secret = "ghp_" + "A" * 36
        self.write([inbox("secret", role_id="lead", project=secret)])
        entry = self.board()["lead_inbox"][0]["by_project"][0]
        self.assertNotIn(secret, entry["project"])
        self.assertIn("[redacted]", entry["project"])

    def test_rule3_waiting_run(self):
        self.write([run("wait-run", state="waiting", started_at=stamp(minutes=-7),
                        updated_at=stamp(seconds=-5))])
        board = self.board()
        item = self.by_id(board["waiting"])["wait-run"]
        self.assertEqual(item["section_reason"], "waits_on")
        self.assertEqual(item["started_age_s"], 420)
        self.assertEqual(board["counts"]["waiting"], 1)
        self.assertEqual(board["running"], [])

    def test_queued_work_is_not_waiting(self):
        self.write([run("queued-run", state="queued"), job("queued-job", state="queued")])
        board = self.board()
        self.assertEqual(sorted(self.by_id(board["queued"])), ["queued-job", "queued-run"])
        self.assertEqual(board["counts"]["queued"], 2)
        self.assertEqual((board["waiting"], board["counts"]["waiting"]), ([], 0))
        self.assertEqual(board["running"], [])

    def test_rule4_lead_wait_job(self):
        self.write([job("wait-job", kind="wait", started_at=stamp(minutes=-2))])
        board = self.board()
        item = self.by_id(board["waiting"])["wait-job"]
        self.assertEqual(item["section_reason"], "lead_wait")
        self.assertEqual((board["counts"]["waiting"], board["counts"]["running"]), (1, 0))

    def test_rule5_wait_worker_is_hidden_when_a_run_covers_it(self):
        self.write([
            run("lead-run", role_id="lead", started_at=stamp(minutes=-3)),
            job("plumbing", kind="wait-worker", role_id="lead",
                started_at=stamp(minutes=-4)),
            job("orphan", kind="wait-worker", role_id="worker",
                started_at=stamp(minutes=-4)),
            run("early-run", role_id="early", started_at=stamp(minutes=-6)),
            job("early-wait", kind="wait-worker", role_id="early",
                started_at=stamp(minutes=-4)),
        ])
        board = self.board()
        waiting = self.by_id(board["waiting"])
        self.assertNotIn("plumbing", waiting)
        self.assertEqual(waiting["orphan"]["section_reason"], "lead_wait")
        self.assertEqual(waiting["early-wait"]["section_reason"], "lead_wait")
        self.assertEqual(board["counts"]["waiting"], 2)  # the hidden job adds nothing
        self.assertEqual(set(self.by_id(board["running"])), {"lead-run", "early-run"})

    def test_rule6_running_newest_started_first_nulls_last(self):
        self.write([run("r-late", started_at=stamp(minutes=-1)),
                    run("r-early", started_at=stamp(minutes=-9))])
        self.put_raw(run("r-null", started_at=None))
        board = self.board()
        self.assertEqual([item["ref"]["id"] for item in board["running"]],
                         ["r-late", "r-early", "r-null"])
        self.assertIsNone(self.by_id(board["running"])["r-null"]["started_age_s"])
        self.assertEqual(board["counts"]["running"], 3)

    def test_rule7_lost_and_stale_exceptions(self):
        self.write([
            run("lost-1", process={"host": "mbp", "pid": 424242}),
            run("stale-1", updated_at=stamp(minutes=-42), observed_at=stamp(minutes=-42)),
            run("old-stale", updated_at=stamp(hours=-30), observed_at=stamp(hours=-30)),
        ])

        class Dead:
            def check(self, process):
                return False

        board = self.board(query.QueryBackend(self.cfg, process_checker=Dead()))
        self.assertEqual([item["ref"]["id"] for item in board["exceptions"]["process_gone"]],
                         ["lost-1"])
        self.assertEqual([item["ref"]["id"] for item in board["exceptions"]["out_of_date"]],
                         ["stale-1"])
        self.assertEqual((board["counts"]["process_gone"],
                          board["counts"]["out_of_date"],
                          board["counts"]["older_unverified"]), (1, 1, 1))
        self.assertEqual(board["recent"], [])

    def test_rule8_unknown_recent_excludes_old_rows(self):
        self.write([run("unknown-1", state="unknown", updated_at=stamp(minutes=-5)),
                    run("old-unknown", state="unknown", updated_at=stamp(hours=-26)),
                    run("old-done", state="done", updated_at=stamp(hours=-26), ended_at=stamp(hours=-26))])
        real_loads = json.loads
        with mock.patch.object(query.json, "loads", wraps=real_loads) as loads:
            board = self.board()
        parsed = "".join(call.args[0] for call in loads.call_args_list)
        self.assertNotIn('"old-unknown"', parsed)
        self.assertNotIn('"old-done"', parsed)
        self.assertEqual([item["ref"]["id"] for item in board["exceptions"]["unverified_recent"]],
                         ["unknown-1"])
        self.assertEqual([item["ref"]["id"] for item in board["projects"][0]["needs_you"]],
                         ["unknown-1"])
        self.assertEqual(board["counts"]["older_unverified"], 1)

    def test_rule9_recent_skips_wait_worker_and_old_terminal(self):
        self.write([
            run("done-1", state="done", updated_at=stamp(minutes=-10),
                ended_at=stamp(minutes=-10)),
            run("failed-1", state="failed", updated_at=stamp(minutes=-5),
                ended_at=stamp(minutes=-5)),
            run("cancelled-1", state="cancelled", updated_at=stamp(minutes=-20),
                ended_at=stamp(minutes=-20)),
            job("plumbing", kind="wait-worker", state="failed",
                updated_at=stamp(minutes=-4), ended_at=stamp(minutes=-4)),
            run("old-done", state="done", updated_at=stamp(hours=-30),
                ended_at=stamp(hours=-30)),
        ])
        board = self.board()
        self.assertEqual([item["ref"]["id"] for item in board["recent"]],
                         ["failed-1", "done-1", "cancelled-1"])
        self.assertEqual(board["counts"]["failed_recent"], 1)
        self.assertEqual(board["counts"]["older_unverified"], 0)
        self.assertFalse(board["truncated"]["recent"])

    def test_rule10_sessions_within_the_window(self):
        self.write([
            session("s-recent", last_activity_at=stamp(seconds=-30)),
            session("s-idle", last_activity_at=stamp(minutes=-120),
                    updated_at=stamp(minutes=-120)),
            session("s-old", last_activity_at=stamp(hours=-30),
                    updated_at=stamp(hours=-30)),
        ])
        board = self.board()
        self.assertEqual([item["ref"]["id"] for item in board["sessions"]],
                         ["s-recent", "s-idle"])
        self.assertEqual(board["sessions_total"], 2)
        self.assertEqual(board["counts"]["sessions_recent"], 1)

    def test_older_boundary_is_updated_ts_before_the_window(self):
        self.write([
            run("edge-done", state="done", updated_at=stamp(hours=-24),
                ended_at=stamp(hours=-24)),
            run("before-done", state="done", updated_at=stamp(hours=-24, seconds=-1),
                ended_at=stamp(hours=-24, seconds=-1)),
        ])
        ids = [item["ref"]["id"] for item in self.board()["recent"]]
        self.assertIn("edge-done", ids)
        self.assertNotIn("before-done", ids)

    def test_caps_set_truncated_but_counts_stay_full(self):
        records = [run(f"run-{index}", started_at=stamp(seconds=-index - 1))
                   for index in range(3)]
        records += [run(f"stale-{index}", updated_at=stamp(minutes=-42),
                        observed_at=stamp(minutes=-42)) for index in range(3)]
        records += [run(f"done-{index}", state="done",
                        updated_at=stamp(seconds=-10 - index),
                        ended_at=stamp(seconds=-10 - index)) for index in range(3)]
        records += [session(f"s-{index}", last_activity_at=stamp(seconds=-10 - index))
                    for index in range(2)]
        records += [inbox(f"i-{index}", role_id="lead", kind="message",
                          created_at=stamp(minutes=-1 - index)) for index in range(2)]
        self.write(records)
        with mock.patch.object(query, "BOARD_LIST_LIMIT", 2), \
                mock.patch.object(query, "BOARD_EXCEPTION_LIMIT", 1), \
                mock.patch.object(query, "BOARD_RECENT_LIMIT", 1), \
                mock.patch.object(query, "BOARD_SESSIONS_LIMIT", 1), \
                mock.patch.object(query, "BOARD_INBOX_ITEMS", 1):
            board = self.board()
        self.assertEqual(len(board["running"]), 2)
        self.assertEqual(len(board["exceptions"]["out_of_date"]), 1)
        self.assertEqual(len(board["recent"]), 1)
        self.assertEqual((len(board["sessions"]), board["sessions_total"]), (1, 2))
        self.assertEqual(len(board["lead_inbox"][0]["items"]), 1)
        self.assertEqual(board["truncated"],
                         {"queued": False, "waiting": False, "running": True, "exceptions": True,
                          "recent": True, "lead_inbox": True})
        self.assertEqual((board["counts"]["running"], board["counts"]["out_of_date"],
                          board["counts"]["failed_recent"],
                          board["counts"]["older_unverified"]), (3, 3, 0, 0))


class RedactionTest(unittest.TestCase):
    """Every free-text field that leaves the server is redacted (spec §9)."""

    def test_secrets_in_title_summary_detail_and_raw_view(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        directory = Path(tmp.name)
        root = directory / "sources"
        root.mkdir()
        cfg = config.Config()
        cfg.roots = [root]
        cfg.db_path = directory / "db.sqlite"
        cfg.harness.enabled = cfg.claude_code.enabled = cfg.codex.enabled = "false"
        conn = store.open_db(cfg.db_path)
        self.addCleanup(conn.close)
        ingestor = ingest.Ingestor(conn, cfg, clock=lambda: NOW)
        secret_run = run(
            "sec-1", title=f"worker {SECRET}",
            summary=f"summary {SECRET}",
            links=[{"label": f"log {SECRET}", "url": "https://example.com/"}],
            x_note=f"nested {SECRET}",
            x_nested={"deep": [f"list {SECRET}"]})
        secret_job = job("sec-j", command_summary=f"run {SECRET}",
                         summary=f"job {SECRET}")
        secret_inbox = inbox("sec-i", detail=f"detail {SECRET}", action_required=True)
        path = root / "work@mbp" / "0000000001.ndjson"
        path.parent.mkdir(parents=True)
        path.write_text("".join(json.dumps(record) + "\n"
                                for record in (secret_run, secret_job, secret_inbox)),
                        encoding="utf-8")
        ingestor.scan_roots()
        backend = query.QueryBackend(cfg)
        snap = backend.snapshot(NOW)
        self.assertNotIn(SECRET, json.dumps(snap))
        self.assertIn("[redacted]", json.dumps(snap))

        detail = backend.record(NOW, "work@mbp", "run", "sec-1")
        dumped = json.dumps(detail)
        self.assertNotIn(SECRET, dumped)
        self.assertEqual(detail["record"]["title"], "worker [redacted]")
        self.assertEqual(detail["record"]["summary"], "summary [redacted]")
        self.assertEqual(detail["record"]["links"],
                         [{"label": "log [redacted]", "url": "https://example.com/"}])
        self.assertEqual(detail["full"]["x_note"], "nested [redacted]")
        self.assertEqual(detail["full"]["x_nested"]["deep"], ["list [redacted]"])

        detail = backend.record(NOW, "work@mbp", "job", "sec-j")
        self.assertEqual(detail["record"]["command_summary"], "run [redacted]")
        self.assertEqual(detail["record"]["summary"], "job [redacted]")
        self.assertNotIn(SECRET, json.dumps(detail))

        detail = backend.record(NOW, "work@mbp", "inbox_item", "sec-i")
        self.assertEqual(detail["record"]["detail"], "detail [redacted]")
        self.assertNotIn(SECRET, json.dumps(detail))

    def test_every_field_of_a_response_is_redacted_but_lookup_ids_are_not(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        directory = Path(tmp.name)
        root = directory / "sources"
        root.mkdir()
        cfg = config.Config()
        cfg.roots = [root]
        cfg.db_path = directory / "db.sqlite"
        cfg.harness.enabled = cfg.claude_code.enabled = cfg.codex.enabled = "false"
        conn = store.open_db(cfg.db_path)
        self.addCleanup(conn.close)
        ingestor = ingest.Ingestor(conn, cfg, clock=lambda: NOW)
        secret_run = run(
            "url-1", project=f"p {SECRET}", model=f"m {SECRET}",
            links=[{"label": "artifact", "url": f"https://example.com/?token={SECRET}"},
                   {"label": "log", "path": f"/tmp/{SECRET}.log"}],
            waits_on=[{"type": "external", "kind": f"k {SECRET}", "key": f"key {SECRET}",
                       "url": f"https://example.com/{SECRET}"}])
        free_form = run("usage-1", usage={"basis": "measured", "id": SECRET,
                                          "source_id": {"api_token": SECRET}})
        secret_session = session("usage-s", usage={"basis": "measured",
                                                   "x_token": {"deep": [SECRET]}})
        path = root / "work@mbp" / "0000000001.ndjson"
        path.parent.mkdir(parents=True)
        path.write_text("".join(json.dumps(record) + "\n"
                                for record in (secret_run, free_form, secret_session)),
                        encoding="utf-8")
        ingestor.scan_roots()
        backend = query.QueryBackend(cfg)
        snap = backend.snapshot(NOW)
        self.assertEqual({item["ref"]["id"] for item in snap["runs"]}, {"url-1", "usage-1"})
        self.assertNotIn(SECRET, json.dumps(snap))
        self.assertEqual(snap["sessions"][0]["usage"]["x_token"]["deep"], ["[redacted]"])
        detail = backend.record(NOW, "work@mbp", "run", "url-1")
        self.assertEqual(detail["record"]["ref"], {"type": "run", "id": "url-1",
                                                   "source_id": "work@mbp"})
        self.assertNotIn(SECRET, json.dumps(detail))
        usage = backend.record(NOW, "work@mbp", "run", "usage-1")
        self.assertEqual(usage["usage"]["id"], "[redacted]")
        self.assertNotIn(SECRET, json.dumps(usage))
        session_detail = backend.record(NOW, "work@mbp", "session", "usage-s")
        self.assertEqual(session_detail["usage"]["x_token"]["deep"], ["[redacted]"])
        self.assertNotIn(SECRET, json.dumps(session_detail))

    def test_long_summary_is_cut_after_redaction(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        directory = Path(tmp.name)
        root = directory / "sources"
        root.mkdir()
        cfg = config.Config()
        cfg.roots = [root]
        cfg.db_path = directory / "db.sqlite"
        cfg.harness.enabled = cfg.claude_code.enabled = cfg.codex.enabled = "false"
        conn = store.open_db(cfg.db_path)
        self.addCleanup(conn.close)
        ingestor = ingest.Ingestor(conn, cfg, clock=lambda: NOW)
        text = SECRET + " " + "x" * 400
        path = root / "work@mbp" / "0000000001.ndjson"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(run("long-1", summary=text)) + "\n"
                        + json.dumps(inbox("long-i", detail=text)) + "\n",
                        encoding="utf-8")
        ingestor.scan_roots()
        backend = query.QueryBackend(cfg)
        snap = backend.snapshot(NOW)
        runs = {item["ref"]["id"]: item for item in snap["runs"]}
        inboxes = {item["ref"]["id"]: item for item in snap["inbox"]}
        self.assertEqual(len(runs["long-1"]["summary"]), 300)
        self.assertTrue(runs["long-1"]["summary"].startswith("[redacted] "))
        self.assertEqual(len(inboxes["long-i"]["detail"]), 300)


class LostTest(unittest.TestCase):
    """A process check that fails turns a run into `lost` (spec §8.2)."""

    def test_lost_uses_the_process_checker_and_keeps_who(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        directory = Path(tmp.name)
        root = directory / "sources"
        root.mkdir()
        cfg = config.Config()
        cfg.roots = [root]
        cfg.db_path = directory / "db.sqlite"
        cfg.harness.enabled = cfg.claude_code.enabled = cfg.codex.enabled = "false"
        conn = store.open_db(cfg.db_path)
        self.addCleanup(conn.close)
        ingestor = ingest.Ingestor(conn, cfg, clock=lambda: NOW)
        path = root / "work@mbp" / "0000000001.ndjson"
        path.parent.mkdir(parents=True)
        records = [
            run("owner-run", role_id="lead"),
            job("orphan-job", process={"host": "mbp", "pid": 424242},
                updated_at=stamp(seconds=-10)),
        ]
        path.write_text("".join(json.dumps(record) + "\n" for record in records),
                        encoding="utf-8")
        ingestor.scan_roots()

        class Dead:
            calls = 0

            def check(self, process):
                Dead.calls += 1
                return False

        backend = query.QueryBackend(cfg, process_checker=Dead())
        snap = backend.snapshot(NOW)
        job_item = {item["ref"]["id"]: item for item in snap["jobs"]}["orphan-job"]
        self.assertEqual(job_item["display_state"], "lost")
        self.assertEqual(job_item["evidence"]["kind"], "process_gone")
        self.assertEqual(snap["counts"]["stale_lost_unknown"], 1)
        entry = snap["attention"][0]
        self.assertEqual((entry["reason"], entry["who"]), ("lost", None))
        self.assertEqual(entry["subject"]["id"], "orphan-job")
        self.assertEqual(entry["subject"]["display_state"], "lost")
        self.assertIn("process gone", entry["text"])

        # The second call inside the cache window does not ask again.
        backend.snapshot(NOW)
        self.assertEqual(Dead.calls, 1)


class DiscontinuityTest(unittest.TestCase):
    """A source problem makes its records `unknown` and adds a source attention row."""

    def test_source_problem_marks_records_unknown_and_lists_the_source(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        directory = Path(tmp.name)
        root = directory / "sources"
        root.mkdir()
        cfg = config.Config()
        cfg.roots = [root]
        cfg.db_path = directory / "db.sqlite"
        cfg.harness.enabled = cfg.claude_code.enabled = cfg.codex.enabled = "false"
        conn = store.open_db(cfg.db_path)
        self.addCleanup(conn.close)
        ingestor = ingest.Ingestor(conn, cfg, clock=lambda: NOW)
        path = root / "work@mbp" / "0000000001.ndjson"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(run("r1", updated_at=stamp(seconds=-10))) + "\n",
                        encoding="utf-8")
        ingestor.scan_roots()
        path.unlink()
        ingestor.scan_roots()

        backend = query.QueryBackend(cfg)
        snap = backend.snapshot(NOW)
        run_item = {item["ref"]["id"]: item for item in snap["runs"]}["r1"]
        self.assertEqual(run_item["display_state"], "unknown")
        self.assertEqual(run_item["evidence"]["kind"], "source_problem")
        source = snap["sources"][0]
        self.assertEqual(source["status"], "discontinuity")
        self.assertIn("all segments are missing", source["detail"])
        entry = snap["attention"][-1]
        self.assertEqual(entry["reason"], "source")
        self.assertEqual(entry["source_id"], "work@mbp")
        self.assertIsNone(entry["who"])
        self.assertIsNone(entry["subject"])
        self.assertIn("discontinuity", entry["text"])


class ExampleFixtureTest(unittest.TestCase):
    """The shipped example files ingest and render as an architecture §4 board."""

    def test_examples_ingest_into_the_board(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        directory = Path(tmp.name)
        root = directory / "sources"
        root.mkdir()
        cfg = config.Config()
        cfg.roots = [root]
        cfg.db_path = directory / "db.sqlite"
        cfg.harness.enabled = cfg.claude_code.enabled = cfg.codex.enabled = "false"
        conn = store.open_db(cfg.db_path)
        self.addCleanup(conn.close)
        ingestor = ingest.Ingestor(conn, cfg, clock=lambda: NOW)

        grouped = {}
        for path in sorted(EXAMPLES.glob("*.ndjson")):
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                record = json.loads(line)
                grouped.setdefault(record["source_id"], []).append(record)
        for source_id, records in grouped.items():
            source_dir = root / source_id
            source_dir.mkdir(parents=True)
            (source_dir / "0000000001.ndjson").write_text(
                "".join(json.dumps(record) + "\n" for record in records),
                encoding="utf-8")
        ingestor.scan_roots()

        backend = query.QueryBackend(cfg)
        snap = backend.snapshot(NOW)
        self.assertEqual(set(snap), SNAPSHOT_KEYS)
        runs = {item["ref"]["id"]: item for item in snap["runs"]}
        jobs = {item["ref"]["id"]: item for item in snap["jobs"]}
        inboxes = {item["ref"]["id"]: item for item in snap["inbox"]}
        sessions = {item["ref"]["id"]: item for item in snap["sessions"]}
        for item in snap["runs"]:
            self.assertEqual(set(item), RUN_KEYS)
        for item in snap["sessions"]:
            self.assertEqual(set(item), SESSION_KEYS)

        self.assertEqual(runs["ds-edd-1-20261105-053128"]["state"], "done")
        self.assertEqual(runs["ds-edd-1-20261105-053128"]["parent_run"]["id"], "lead-7f3a")
        self.assertEqual(runs["lead-9c21"]["display_state"], "stale")
        self.assertEqual(runs["lead-9c21"]["waits_on"][0]["type"], "external")
        self.assertEqual(jobs["lw-store-blink-20261105-053128"]["run"]["id"], "lead-7f3a")
        self.assertEqual(inboxes["ev-20261105-054742-54fd"]["state"], "acked")
        self.assertEqual(inboxes["ev-20261105-054742-54fd"]["outcome"], "done")
        self.assertEqual(sessions["s-ended"]["display_state"], "ended")
        self.assertEqual(sessions["019a5c2e-7d1b-7c40-9f1e-2b8d1e4c9a10"]["turn_open"], True)
        self.assertFalse(snap["demo"])

        links = runs["ds-edd-1-20261105-053128"]["links"]
        self.assertEqual(links[0]["label"], "worker log")
        self.assertFalse(links[0]["readable"])  # /Users/me is outside the allowed roots
        self.assertEqual(links[1]["url"],
                         "https://github.com/nurockplayer/eddington-1919/pull/176")

        record = backend.record(NOW, "my-workflow@mbp", "run",
                                "ds-edd-1-20261105-053128")
        self.assertEqual(set(record), RECORD_KEYS)
        self.assertEqual(record["relations"]["parent"]["id"], "lead-7f3a")
        self.assertEqual(record["relations"]["inbox"], [])


if __name__ == "__main__":
    unittest.main()
