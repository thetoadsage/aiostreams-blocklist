import datetime
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import health

NOW = datetime.datetime(2026, 11, 2, 18, tzinfo=datetime.timezone.utc)


class HealthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def record(self, code=0, outcome='unchanged', commit='abc', now=NOW, stage='complete'):
        health.record(self.root, code, outcome, commit, now.isoformat(), stage, now)

    def state(self):
        return json.loads((self.root / 'last-run.json').read_text())

    def test_failure_preserves_last_success_and_recovery_clears_failures(self):
        self.record()
        self.record(1, 'failed', '', stage='aggregate')
        self.record(1, 'failed', '', stage='fetch')
        state = self.state()
        self.assertEqual(state['last_success_at'], NOW.isoformat())
        self.assertEqual(state['last_success_commit'], 'abc')
        self.assertEqual(state['consecutive_failures'], 2)
        healthy, message = health.check(self.root, now=NOW)
        self.assertFalse(healthy)
        self.assertIn('fetch', message)
        self.record(commit='def')
        self.assertTrue(health.check(self.root, now=NOW)[0])
        self.assertEqual(self.state()['consecutive_failures'], 0)
        self.assertEqual(self.state()['last_success_commit'], 'def')

    def test_overdue_success_is_unhealthy_even_without_new_failures(self):
        self.record(now=NOW - datetime.timedelta(hours=9))
        self.assertIn('overdue', health.check(self.root, now=NOW)[1])
        self.assertTrue(health.check(self.root, max_age_hours=10, now=NOW)[0])

    def test_missing_invalid_and_future_state_is_unhealthy(self):
        self.assertFalse(health.check(self.root, now=NOW)[0])
        for content in ['broken', '[]', '{"exit_code":1}',
                        '{"exit_code":0,"outcome":"unchanged","finished_at":123}']:
            (self.root / 'last-run.json').write_text(content)
            self.assertFalse(health.check(self.root, now=NOW)[0])
        self.record(now=NOW + datetime.timedelta(hours=1))
        self.assertIn('future', health.check(self.root, now=NOW)[1])

    def test_old_state_format_survives_upgrade_and_failed_run(self):
        (self.root / 'last-run.json').write_text(json.dumps({
            'exit_code': 0, 'outcome': 'updated', 'commit': 'old',
            'finished_at': NOW.isoformat()}))
        self.assertTrue(health.check(self.root, now=NOW)[0])
        self.record(1, 'failed', '')
        self.assertEqual(self.state()['last_success_commit'], 'old')


if __name__ == '__main__':
    unittest.main()
