"""Real producer shapes: directory labels shared by jobs, ledgers and sessions."""
import json
import tempfile
import unittest
from pathlib import Path

from fleetglint import config, ingest, store
from tests.test_adapter_harness import LEDGER_HEADER, NOW, make_state, write_job


class ProjectAttributionTest(unittest.TestCase):
    def test_existing_scratch_labels_are_global_across_producers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = make_state(tmp)
            paths = {}
            for name in ("review-20261101", "routing-20261101", "taskbox", "ops-data",
                         "real-app", "configured-app", "mapped-20261101"):
                path = root / name
                path.mkdir()
                paths[name] = path
                if name != "review-20261101":
                    (path / ".git").mkdir()
                    (path / ".git/config").write_text('[core]\n\tbare = false\n')
            (paths["real-app"] / ".git/config").write_text(
                '[remote "origin"]\n\turl = https://example.org/team/real-app.git\n'
                '\tfetch = +refs/heads/*:refs/remotes/origin/*\n'
                '\tfetch = +refs/notes/*:refs/notes/*\n\tpromisor\n')
            paths["deleted-app"] = root / "deleted-app"
            expected = {name: None for name in paths}
            expected.update({"real-app": "real-app", "configured-app": "configured-app",
                             "mapped-20261101": "configured-app", "deleted-app": "deleted-app"})
            rows = []
            for index, (name, path) in enumerate(paths.items()):
                # A completed ledger row has a project label but no cwd.
                rows.append(f'2026-11-05 06:00 JST\t2026-11-05 06:01 JST\tcx\t{name}\t'
                            f'worker-{index}\tmodel\t-\t0\tdone\t-\n')
                # taskbox is evidenced only by a Codex session, like a scratch test repo.
                if name != "taskbox":
                    directory = write_job(state, name, ["true"], result=json.dumps({
                        "started": "2026-11-05T06:00:00+09:00",
                        "ended": "2026-11-05T06:01:00+09:00", "exit_code": 0, "status": "ok"}))
                    (directory / "cwd").write_text(str(path) + '\n')
                    if name != "review-20261101":
                        (directory / "project").write_text(name + '\n')
            # Explicit project files win both inside another repo and without a remote.
            for job_id, cwd in (("frontend-in-tools", paths["real-app"]),
                                ("frontend-local", paths["ops-data"])):
                directory = write_job(state, job_id, ["true"])
                (directory / "cwd").write_text(str(cwd) + '\n')
                (directory / "project").write_text('frontend\n')
            # A CI repo slug is explicit even when a scratch directory shares its name.
            ci = state / 'ci-watch'
            ci.mkdir()
            (ci / 'runs.tsv').write_text('header\n' + '\t'.join([
                '2026-11-05T06:01:00+09:00', 'team/taskbox', '42', 'Build', 'main',
                'push', 'completed', 'success', '2026-11-05T06:00:00+09:00',
                '2026-11-05T06:01:00+09:00',
                'https://github.com/team/taskbox/actions/runs/42', '-']) + '\n')
            (state / 'worker-ledger/runs.tsv').write_text(LEDGER_HEADER + ''.join(rows))
            test_root = state / 'tachi-run'
            test_root.mkdir()
            (test_root / 'runs.tsv').write_text(
                '1793847600\t123\tThu Nov  5 02:00:00 2026\ttaskbox\tcheck\t0\n')
            sessions = root / 'codex/sessions'
            sessions.mkdir(parents=True)
            (sessions / 'rollout-session.jsonl').write_text(json.dumps({
                'timestamp': '2026-11-05T06:00:00+09:00', 'type': 'session_meta',
                'payload': {'id': '11111111-1111-4111-8111-111111111111',
                            'cwd': str(paths['taskbox'])}}) + '\n')
            duplicate = root / 'scratch/real-app'
            (duplicate / '.git').mkdir(parents=True)
            (sessions / 'rollout-duplicate.jsonl').write_text(json.dumps({
                'timestamp': '2026-11-05T06:00:00+09:00', 'type': 'session_meta',
                'payload': {'id': '22222222-2222-4222-8222-222222222222',
                            'cwd': str(duplicate)}}) + '\n')
            cfg = config.Config()
            cfg.harness.state_dir = state
            cfg.harness.role_projects = {'local': 'configured-app'}
            cfg.harness.path_projects = {str(paths['mapped-20261101']): 'configured-app'}
            cfg.claude_code.enabled = 'false'
            cfg.codex.dir = root / 'codex'
            cfg.db_path = root / 'board.sqlite'
            conn = store.open_db(cfg.db_path)
            try:
                ingestor = ingest.Ingestor(conn, cfg, adapters=ingest.default_adapters(cfg),
                                           clock=lambda: NOW)
                ingestor.scan_adapters()
                records = [json.loads(row[0]) for row in conn.execute('SELECT json FROM records')]
                self.assertEqual(len(records), 2 * len(paths) + 6)
                for record in records:
                    if record['id'].startswith('frontend-'):
                        self.assertEqual(record['project'], 'frontend')
                        continue
                    if record.get('kind') == 'github-actions':
                        self.assertEqual(record['project'], 'taskbox')
                        continue
                    if record['type'] == 'job' and record['id'] in paths and record['id'] != 'review-20261101':
                        self.assertEqual(record['project'], record['id'])
                        continue
                    if record['type'] == 'run':
                        name = list(paths)[int(record['title'].split('-')[1])]
                    elif record['id'] == '22222222-2222-4222-8222-222222222222':
                        name = 'real-app'
                    elif record['type'] == 'session' or record.get('kind') == 'tachi-run':
                        name = 'taskbox'
                    else:
                        name = record['id']
                    with self.subTest(type=record['type'], name=name):
                        self.assertEqual(record.get('project'), expected[name])
            finally:
                conn.close()
