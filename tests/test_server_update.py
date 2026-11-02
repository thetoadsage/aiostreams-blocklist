"""Exercise the real shell runner against disposable local Git repositories."""
import fcntl
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('flock'), 'Linux flock is required by the server runner')
class ServerRunnerTests(unittest.TestCase):
    def git(self, *args, cwd=None):
        return subprocess.check_output(['git', *args], cwd=cwd, stderr=subprocess.PIPE, text=True).strip()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        seed = self.root / 'seed'
        self.git('init', '-b', 'main', str(seed))
        self.git('config', 'user.name', 'Runner test', cwd=seed)
        self.git('config', 'user.email', 'test@example.invalid', cwd=seed)
        (seed / 'scripts').mkdir()
        (seed / 'tests').mkdir()
        (seed / 'tests' / 'test_fixture.py').write_text(
            "import os, unittest\n"
            "class FixtureTest(unittest.TestCase):\n"
            "    def test_gate(self): self.assertFalse(os.environ.get('RUNNER_TEST_TEST_FAIL'))\n")
        (seed / 'scripts' / 'aggregate.py').write_text(
            "import os, pathlib, subprocess, sys, time\n"
            "if os.environ.get('RUNNER_TEST_FAIL'): sys.exit(2)\n"
            "if os.environ.get('RUNNER_TEST_WAIT'):\n"
            "    pathlib.Path(os.environ['RUNNER_TEST_WAIT']).touch()\n"
            "    time.sleep(30)\n"
            "if os.environ.get('RUNNER_TEST_COMPETITOR'):\n"
            "    other = pathlib.Path(os.environ['RUNNER_TEST_COMPETITOR'])\n"
            "    (other / 'concurrent.txt').write_text('preserve me')\n"
            "    for args in [['add', 'concurrent.txt'], ['-c', 'commit.gpgsign=false', 'commit', '-m', 'Concurrent change'], ['push', 'origin', 'main']]:\n"
            "        subprocess.run(['git', *args], cwd=other, check=True, capture_output=True)\n"
            "for name in ['blocklist-all.ndjson', 'blocklist-all.ndjson.gz', 'manifest.json']:\n"
            "    pathlib.Path(name).write_text(os.environ.get('RUNNER_TEST_CONTENT', 'original'))\n")
        for name in ['blocklist-all.ndjson', 'blocklist-all.ndjson.gz', 'manifest.json']:
            (seed / name).write_text('original')
        self.git('add', '.', cwd=seed)
        self.git('-c', 'commit.gpgsign=false', 'commit', '-m', 'Fixture', cwd=seed)
        self.origin = self.root / 'origin.git'
        self.git('clone', '--bare', str(seed), str(self.origin))
        self.app = self.root / 'app'
        self.app.mkdir()
        self.git('clone', '--bare', str(self.origin), str(self.app / 'repository.git'))
        self.git('--git-dir=' + str(self.app / 'repository.git'), 'config', 'commit.gpgsign', 'false')
        shutil.copy(ROOT / 'scripts' / 'health.py', self.app / 'health.py')
        self.initial_commit = self.git('--git-dir=' + str(self.origin), 'rev-parse', 'main')

    def run_update(self, **variables):
        env = {**os.environ, **variables}
        result = subprocess.run(['bash', str(ROOT / 'scripts' / 'server-update.sh'), str(self.app)],
                                env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(list((self.app / 'runs').iterdir()), [])
        return result

    def state(self):
        return json.loads((self.app / 'last-run.json').read_text())

    def head(self):
        return self.git('--git-dir=' + str(self.origin), 'rev-parse', 'main')

    def test_unchanged_run_does_not_commit_and_changed_run_publishes(self):
        result = self.run_update()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.state()['outcome'], 'unchanged')
        self.assertEqual(self.head(), self.initial_commit)
        result = self.run_update(RUNNER_TEST_CONTENT='new')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.state()['outcome'], 'updated')
        self.assertEqual(self.state()['commit'], self.head())
        self.assertNotEqual(self.head(), self.initial_commit)
        self.assertEqual(self.git('--git-dir=' + str(self.origin), 'show', 'main:manifest.json'), 'new')

    def test_aggregation_failure_preserves_remote_and_records_stage(self):
        result = self.run_update(RUNNER_TEST_FAIL='1')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.head(), self.initial_commit)
        self.assertEqual(self.state()['outcome'], 'failed')
        self.assertEqual(self.state()['stage'], 'aggregate')

    def test_test_failure_blocks_aggregation_and_publication(self):
        result = self.run_update(RUNNER_TEST_TEST_FAIL='1', RUNNER_TEST_CONTENT='new')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.head(), self.initial_commit)
        self.assertEqual(self.state()['stage'], 'tests')

    def test_rejected_push_records_failure_without_losing_remote(self):
        hook = self.origin / 'hooks' / 'pre-receive'
        hook.write_text('#!/bin/sh\nexit 1\n')
        hook.chmod(0o700)
        result = self.run_update(RUNNER_TEST_CONTENT='new')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.head(), self.initial_commit)
        self.assertEqual(self.state()['stage'], 'push')
        self.assertEqual(self.state()['outcome'], 'failed')

    def test_lock_skips_second_run_without_overwriting_state(self):
        path = self.app / 'last-run.json'
        path.write_text('existing state')
        with (self.app / 'update.lock').open('w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = self.run_update()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('already running', result.stdout)
        self.assertEqual(path.read_text(), 'existing state')

    def test_concurrent_remote_change_is_preserved_and_retry_starts_fresh(self):
        competitor = self.root / 'competitor'
        self.git('clone', str(self.origin), str(competitor))
        self.git('config', 'user.name', 'Concurrent test', cwd=competitor)
        self.git('config', 'user.email', 'test@example.invalid', cwd=competitor)
        result = self.run_update(RUNNER_TEST_CONTENT='new', RUNNER_TEST_COMPETITOR=str(competitor))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.state()['stage'], 'push')
        self.assertEqual(self.git('--git-dir=' + str(self.origin), 'show', 'main:concurrent.txt'), 'preserve me')
        self.assertEqual(self.git('--git-dir=' + str(self.origin), 'show', 'main:manifest.json'), 'original')
        result = self.run_update(RUNNER_TEST_CONTENT='new')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.git('--git-dir=' + str(self.origin), 'show', 'main:concurrent.txt'), 'preserve me')
        self.assertEqual(self.state()['outcome'], 'updated')

    def test_termination_records_failure_and_cleans_worktree(self):
        marker = self.root / 'aggregating'
        env = {**os.environ, 'RUNNER_TEST_WAIT': str(marker)}
        process = subprocess.Popen(['bash', str(ROOT / 'scripts' / 'server-update.sh'), str(self.app)],
                                   env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, start_new_session=True)
        try:
            deadline = time.monotonic() + 10
            while not marker.exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertTrue(marker.exists(), 'Runner did not reach aggregation')
            os.killpg(process.pid, signal.SIGTERM)
            process.communicate(timeout=10)
            self.assertEqual(process.returncode, 143)
            self.assertEqual(self.state()['stage'], 'aggregate')
            self.assertEqual(self.state()['outcome'], 'failed')
            self.assertEqual(list((self.app / 'runs').iterdir()), [])
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
            process.communicate()


if __name__ == '__main__':
    unittest.main()
