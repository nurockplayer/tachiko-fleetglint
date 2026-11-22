"""Real producer shapes: directory labels shared by jobs, ledgers and sessions."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fleetglint import config, ingest, projects, store
from tests.test_adapter_harness import LEDGER_HEADER, NOW, make_state, write_job


class ProjectAttributionTest(unittest.TestCase):
    def test_project_cache_skips_unchanged_paths_and_refreshes_remote_and_head(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "app"
            git = root / ".git"
            git.mkdir(parents=True)
            config_path = git / "config"
            config_path.write_text('[core]\n\tbare = false\n')
            head = git / "HEAD"
            head.write_text("ref: refs/heads/main\n")
            cache = projects.ProjectCache()
            with mock.patch.object(projects, "_git_repo_name", wraps=projects._git_repo_name) as resolve:
                self.assertEqual(cache(str(root)), "app")
                self.assertIsNone(cache.repo_name(str(root), require_remote=True))
                calls = resolve.call_count
                cache.begin_scan()
                self.assertEqual(cache(str(root)), "app")
                self.assertIsNone(cache.repo_name(str(root), require_remote=True))
                self.assertEqual(resolve.call_count, calls)
                config_path.write_text('[remote "origin"]\n\turl = https://example.org/app.git\n')
                cache.begin_scan()
                self.assertEqual(cache.repo_name(str(root), require_remote=True), "app")
                self.assertGreater(resolve.call_count, calls)
                config_path.write_text('[remote "origin"]\n\turl =\n')
                cache.begin_scan()
                self.assertIsNone(cache.repo_name(str(root), require_remote=True))
                calls = resolve.call_count
                head.write_text("ref: refs/heads/work\n")
                cache.begin_scan()
                self.assertIsNone(cache.repo_name(str(root), require_remote=True))
                self.assertGreater(resolve.call_count, calls)

    def test_project_cache_tracks_retargeted_worktree_and_common_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            worktree = root / "checkout"
            worktree.mkdir()
            for name in ("one", "two"):
                metadata = root / name / ".git/worktrees/checkout"
                metadata.mkdir(parents=True)
                (metadata / "HEAD").write_text("ref: refs/heads/work\n")
                (root / name / ".git/config").write_text(
                    '[remote "origin"]\n\turl = https://example.org/repo.git\n')
            pointer = worktree / ".git"
            pointer.write_text(f"gitdir: {root}/one/.git/worktrees/checkout\n")
            cache = projects.ProjectCache()
            self.assertEqual(cache(str(worktree)), "one")
            pointer.write_text(f"gitdir: {root}/two/.git/worktrees/checkout\n")
            cache.begin_scan()
            self.assertEqual(cache(str(worktree)), "two")
            self.assertEqual(cache.repo_name(str(worktree), require_remote=True), "two")
            (root / "two/.git/config").write_text('[core]\n\tbare = false\n')
            cache.begin_scan()
            self.assertIsNone(cache.repo_name(str(worktree), require_remote=True))

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
            build = root / 'build'
            build.mkdir()
            for job_id, cwd in (("frontend-in-tools", paths["real-app"]),
                                ("frontend-local", paths["ops-data"]),
                                ("frontend-build", build),
                                ("frontend-deleted", root / 'gone/frontend')):
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
            with (state / 'worker-ledger/runs.tsv').open('a') as ledger:
                ledger.write('2026-11-05 06:00 JST\t2026-11-05 06:01 JST\tcx\tdesign-system\t'
                             'override\tmodel\t-\t0\tdone\t-\n')
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
            # Another repo named frontend must not rewrite the two explicit frontend jobs.
            frontend = root / 'frontend'
            (frontend / '.git').mkdir(parents=True)
            (sessions / 'rollout-frontend.jsonl').write_text(json.dumps({
                'timestamp': '2026-11-05T06:00:00+09:00', 'type': 'session_meta',
                'payload': {'id': '33333333-3333-4333-8333-333333333333',
                            'cwd': str(frontend)}}) + '\n')
            (sessions / 'rollout-deleted.jsonl').write_text(json.dumps({
                'timestamp': '2026-11-05T06:00:00+09:00', 'type': 'session_meta',
                'payload': {'id': '44444444-4444-4444-8444-444444444444',
                            'cwd': str(root / 'gone/frontend')}}) + '\n')
            claude = root / 'claude/synthetic'
            claude.mkdir(parents=True)
            (claude / '55555555-5555-4555-8555-555555555555.jsonl').write_text(json.dumps({
                'type': 'user', 'timestamp': '2026-11-05T06:00:00+09:00',
                'sessionId': '55555555-5555-4555-8555-555555555555',
                'cwd': str(root / 'gone/frontend')}) + '\n')
            cfg = config.Config()
            cfg.harness.state_dir = state
            cfg.harness.role_projects = {'local': 'configured-app'}
            cfg.harness.path_projects = {str(paths['mapped-20261101']): 'configured-app'}
            cfg.claude_code.dir = root / 'claude'
            cfg.codex.dir = root / 'codex'
            cfg.db_path = root / 'board.sqlite'
            conn = store.open_db(cfg.db_path)
            try:
                ingestor = ingest.Ingestor(conn, cfg, adapters=ingest.default_adapters(cfg),
                                           clock=lambda: NOW)
                # Runtime attribution must work with no Git executable available.
                with mock.patch.dict(os.environ, {'PATH': ''}):
                    ingestor.scan_adapters()
                records = [json.loads(row[0]) for row in conn.execute('SELECT json FROM records')]
                self.assertEqual(len(records), 2 * len(paths) + 12)
                for record in records:
                    if record['id'] in {'44444444-4444-4444-8444-444444444444',
                                        '55555555-5555-4555-8555-555555555555'}:
                        self.assertEqual(record['project'], 'frontend')
                        continue
                    if record.get('title') == 'override':
                        self.assertEqual(record['project'], 'design-system')
                        continue
                    if record['id'] == '33333333-3333-4333-8333-333333333333':
                        self.assertNotIn('project', record)
                        continue
                    if record['id'].startswith('frontend-'):
                        self.assertEqual(record['project'], 'frontend')
                        continue
                    if record.get('kind') == 'github-actions':
                        self.assertEqual(record['project'], 'taskbox')
                        continue
                    if record['type'] == 'run':
                        name = list(paths)[int(record['title'].split('-')[1])]
                        if name == 'review-20261101':
                            # Without a repo basename, this saved assignment has no proof
                            # of having been directory-derived.
                            self.assertEqual(record['project'], name)
                            continue
                    elif record['id'] == '22222222-2222-4222-8222-222222222222':
                        self.assertNotIn('project', record)
                        continue
                    elif record['type'] == 'session' or record.get('kind') == 'tachi-run':
                        name = 'taskbox'
                    else:
                        name = record['id']
                    with self.subTest(type=record['type'], name=name):
                        self.assertEqual(record.get('project'), expected[name])
            finally:
                conn.close()

    def test_remote_url_values_follow_git_rules(self):
        for value, expected in (('https://example.org/team/app.git', True),
                                ("/srv/it's-a-repo.git", True),
                                ('"/srv/it\'s a repo.git"', True),
                                ('"/srv/a \\"quoted\\" repo.git"', True),
                                ('"#not-a-comment"', True),
                                ('/srv/app.git ; comment', True),
                                ('/srv/app.git # comment', True),
                                ('; only a comment', False),
                                ('# only a comment', False),
                                ('""', False),
                                # Git rejects these lines, so they name no remote.
                                ('"/srv/unclosed.git', False),
                                ('/srv/bad\\q.git', False)):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as tmp:
                git_dir = Path(tmp)
                (git_dir / 'config').write_text(f'[remote "origin"]\n\turl = {value}\n')
                self.assertEqual(projects._has_remote(git_dir), expected)

    def test_apostrophe_remote_keeps_the_scan_going(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = make_state(tmp)
            configs = {'quoted-app': "[remote \"origin\"]\n\turl = /srv/it's-a-repo.git\n",
                       'real-app': '[remote "origin"]\n\turl = https://example.org/team/real-app.git\n',
                       'scratch-app': '[core]\n\tbare = false\n'}
            for name, text in configs.items():
                (root / name / '.git').mkdir(parents=True)
                (root / name / '.git/config').write_text(text)
                directory = write_job(state, name, ['true'])
                (directory / 'cwd').write_text(str(root / name) + '\n')
                (directory / 'project').write_text(name + '\n')
            cfg = config.Config()
            cfg.harness.state_dir = state
            cfg.claude_code.dir = root / 'claude'
            cfg.codex.dir = root / 'codex'
            cfg.db_path = root / 'board.sqlite'
            conn = store.open_db(cfg.db_path)
            try:
                ingest.Ingestor(conn, cfg, adapters=ingest.default_adapters(cfg),
                                clock=lambda: NOW).scan_adapters()
                projects_by_id = {record['id']: record.get('project') for record in (
                    json.loads(row[0]) for row in conn.execute('SELECT json FROM records'))}
            finally:
                conn.close()
        self.assertEqual(projects_by_id, {'quoted-app': 'quoted-app', 'real-app': 'real-app',
                                          'scratch-app': None})
