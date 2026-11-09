import gzip
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import aggregate
import update

KEY = 'wd1:' + 'a' * 32


def row(verdict='dead', hosts=None, n=1, at=100):
    return {'k': KEY, 'v': verdict, 'n': n, 'at': at, 'bk': hosts or []}


class AggregationTests(unittest.TestCase):
    def test_rejects_duplicate_live_and_pinned_gist_before_fetch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            urls = ['https://gist.githubusercontent.com/owner/123/raw/blocks.ndjson',
                    'https://gist.githubusercontent.com/owner/123/raw/abc/blocks.ndjson']
            (root / 'sources.json').write_text(json.dumps(urls))
            with mock.patch.object(aggregate, 'ROOT', root), mock.patch.object(aggregate, 'load_baseline', return_value=[row()]), mock.patch.object(aggregate, 'fetch') as fetch:
                with self.assertRaisesRegex(ValueError, 'Duplicate source'):
                    aggregate.main()
                fetch.assert_not_called()

    def test_distinct_gist_files_and_contributors_remain_valid(self):
        aggregate.validate_sources(['https://gist.githubusercontent.com/owner/123/raw/a.ndjson',
                                    'https://gist.githubusercontent.com/owner/123/raw/b.ndjson',
                                    'https://gist.githubusercontent.com/other/456/raw/a.ndjson'])
        aggregate.validate_sources(json.loads((aggregate.ROOT / 'sources.json').read_text()))

    def test_invalid_source_configuration_fails_early(self):
        for urls in [[], {}, [1], ['http://example.com/a'], ['https://user:secret@example.com/a'],
                     ['https://example.com/a', 'https://example.com/a']]:
            with self.subTest(urls=urls), self.assertRaises(ValueError):
                aggregate.validate_sources(urls)

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

    def test_baseline_retained_when_sources_remove_entries(self):
        original = row(hosts=['original.example'], n=4)
        added = {**row(), 'k': 'nh1:' + 'b' * 40}
        first = aggregate.with_baseline([original], [row(hosts=['new.example'], n=2), added])
        self.assertEqual(len(first), 2)
        saved = next(r for r in first if r['k'] == KEY)
        self.assertEqual(saved['bk'], ['new.example', 'original.example'])
        self.assertEqual(saved['n'], 4)
        # Removing the baseline key upstream never removes the original block.
        self.assertEqual(aggregate.with_baseline([original], [added]), aggregate.merge([[original, added]]))
        self.assertEqual(first, aggregate.with_baseline([original], [row(hosts=['new.example'], n=2), added]))

    def test_corrupt_baseline_fails_before_fetching(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / aggregate.BASELINE_FILE
            path.parent.mkdir()
            path.write_bytes(gzip.compress(b'changed'))
            with mock.patch.object(aggregate, 'ROOT', root), mock.patch.object(aggregate, 'fetch') as fetch:
                with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
                    aggregate.main()
                fetch.assert_not_called()

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
            with mock.patch.object(aggregate, 'ROOT', root), mock.patch.object(aggregate, 'fetch', fetch), mock.patch.object(aggregate, 'load_baseline', return_value=[row()]):
                with self.assertRaisesRegex(RuntimeError, 'Published files unchanged'):
                    aggregate.main()
            for name in ['blocklist-all.ndjson', 'blocklist-all.ndjson.gz', 'manifest.json']:
                self.assertEqual((root / name).read_bytes(), b'original')

    def test_successful_update_validates_and_preserves_native_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'sources.json').write_text('["https://example.com/a"]')
            rows = [row(), {**row(), 'k': 'nh1:' + 'b' * 40}]
            manual = {**row(), 'k': 'wd1:' + 'c' * 32, 'bk': ['eweka.nl']}
            snapshot = root / aggregate.SCREENER_SNAPSHOT
            snapshot.parent.mkdir()
            snapshot.write_bytes(aggregate.serialize([manual]))
            with mock.patch.object(aggregate, 'ROOT', root), mock.patch.object(aggregate, 'fetch', return_value=rows), mock.patch.object(aggregate, 'load_baseline', return_value=[row()]):
                aggregate.main()
            plain = (root / 'blocklist-all.ndjson').read_bytes()
            self.assertEqual(gzip.decompress((root / 'blocklist-all.ndjson.gz').read_bytes()), plain)
            self.assertEqual(len(aggregate.parse(plain)), 3)
            self.assertIn(manual, aggregate.parse(plain))
            manifest = json.loads((root / 'manifest.json').read_text())
            self.assertEqual(manifest['entries'], 3)
            self.assertEqual(manifest['aggregation']['mode'], 'baseline-plus-mirror')


class ManualUpdateTests(unittest.TestCase):
    def test_partial_export_keeps_baseline_scope_severity_and_counts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            export = root / 'partial.ndjson'
            extra = {**row(), 'k': 'nh1:' + 'b' * 40}
            export.write_bytes(aggregate.serialize([row('defective', ['new.example'], n=2), extra]))
            baseline = [row('dead', ['original.example'], n=4),
                        {**row(), 'k': 'wd1:' + 'c' * 32}]
            with mock.patch.object(update, 'ROOT', root), mock.patch.object(aggregate, 'load_baseline', return_value=baseline), mock.patch.object(sys, 'argv', ['update.py', str(export)]):
                update.main()
            result = {r['k']: r for r in aggregate.parse((root / 'blocklist-all.ndjson').read_bytes())}
            self.assertEqual(len(result), 3)
            self.assertEqual(result[KEY], row('dead', ['new.example', 'original.example'], n=4))
            self.assertEqual(gzip.decompress((root / 'blocklist-all.ndjson.gz').read_bytes()), (root / 'blocklist-all.ndjson').read_bytes())
            self.assertEqual(json.loads((root / 'manifest.json').read_text())['aggregation']['mode'], 'baseline-plus-export')

    def test_missing_or_corrupt_baseline_preserves_published_files(self):
        for corrupt in (False, True):
            with self.subTest(corrupt=corrupt), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                export = root / 'partial.ndjson'
                export.write_bytes(aggregate.serialize([row()]))
                if corrupt:
                    path = root / aggregate.BASELINE_FILE
                    path.parent.mkdir()
                    path.write_bytes(gzip.compress(b'changed'))
                names = ['blocklist-all.ndjson', 'blocklist-all.ndjson.gz', 'manifest.json']
                for name in names:
                    (root / name).write_bytes(b'original')
                with mock.patch.object(update, 'ROOT', root), mock.patch.object(sys, 'argv', ['update.py', str(export)]):
                    with self.assertRaises((OSError, ValueError)):
                        update.main()
                for name in names:
                    self.assertEqual((root / name).read_bytes(), b'original')


if __name__ == '__main__':
    unittest.main()
