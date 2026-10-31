import gzip
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import aggregate

KEY = 'wd1:' + 'a' * 32


def row(verdict='dead', hosts=None, n=1, at=100):
    return {'k': KEY, 'v': verdict, 'n': n, 'at': at, 'bk': hosts or []}


class AggregationTests(unittest.TestCase):
    def test_native_and_compressed_warden_are_equivalent(self):
        native = b'{"blocklist":1}\n' + json.dumps(row(hosts=['news.example.com'])).encode()
        warden = b'{"warden":1}\n' + json.dumps({
            'fp': KEY, 'deadAt': 100, 'n': 1, 'bk': ['news.example.com']}).encode()
        self.assertEqual(aggregate.parse(native), aggregate.parse(gzip.compress(warden)))

    def test_merge_matches_aiostreams_scope_severity_and_counts(self):
        merged = aggregate.merge([
            [row(hosts=['a.example'], n=999999999)],
            [row('fake', ['b.example'], n=5, at=200)]])
        self.assertEqual(merged, [row('fake', ['a.example', 'b.example'], n=1000000000, at=200)])
        self.assertEqual(aggregate.merge([merged, [row()]])[0]['bk'], [])

    def test_mirror_drops_old_keys_and_does_not_recount_previous_runs(self):
        other = {**row(), 'k': 'nh1:' + 'b' * 40}
        self.assertEqual(len(aggregate.merge([[row(), other]])), 2)
        current = aggregate.merge([[row(n=3)]])
        self.assertEqual(current, [row(n=3)])
        self.assertEqual(aggregate.serialize(current), aggregate.serialize(aggregate.merge([[row(n=3)]])))

    def test_rejects_empty_invalid_and_truncated_sources(self):
        for body in [b'', b'<html>error</html>', b'{"warden":1}\n',
                     b'{"warden":1}\n{"fp":"invalid"}',
                     b'{"blocklist":1}\n{"k":', gzip.compress(b'{"warden":1}\n')[:-4]]:
            with self.subTest(body=body), self.assertRaises(Exception):
                aggregate.parse(body)

    def test_source_failure_keeps_published_files_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'sources.json').write_text(json.dumps(['https://example.com/a', 'https://example.com/b']))
            for name in ['blocklist-all.ndjson', 'blocklist-all.ndjson.gz', 'manifest.json']:
                (root / name).write_bytes(b'original')
            def fetch(url):
                if url.endswith('/a'):
                    return [row()]
                raise ValueError('source unavailable')
            with mock.patch.object(aggregate, 'ROOT', root), mock.patch.object(aggregate, 'fetch', fetch):
                with self.assertRaisesRegex(RuntimeError, 'Published files unchanged'):
                    aggregate.main()
            for name in ['blocklist-all.ndjson', 'blocklist-all.ndjson.gz', 'manifest.json']:
                self.assertEqual((root / name).read_bytes(), b'original')

    def test_successful_update_validates_and_preserves_native_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'sources.json').write_text('["https://example.com/a"]')
            rows = [row(), {**row(), 'k': 'nh1:' + 'b' * 40}]
            with mock.patch.object(aggregate, 'ROOT', root), mock.patch.object(aggregate, 'fetch', return_value=rows):
                aggregate.main()
            plain = (root / 'blocklist-all.ndjson').read_bytes()
            self.assertEqual(gzip.decompress((root / 'blocklist-all.ndjson.gz').read_bytes()), plain)
            self.assertEqual(len(aggregate.parse(plain)), 2)
            manifest = json.loads((root / 'manifest.json').read_text())
            self.assertEqual(manifest['entries'], 2)
            self.assertEqual(manifest['aggregation']['mode'], 'mirror')


if __name__ == '__main__':
    unittest.main()
