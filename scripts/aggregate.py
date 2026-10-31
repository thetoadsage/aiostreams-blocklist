#!/usr/bin/env python3
"""Preserve the original baseline and combine it with current public sources."""
import concurrent.futures
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import tempfile
import time
import urllib.request

import update

ROOT = Path(__file__).resolve().parents[1]
SEVERITY = {'defective': 1, 'dead': 2, 'mislabeled': 3, 'fake': 4}
MAX_DOWNLOAD = 64 * 1024 * 1024
MAX_DECOMPRESSED = 256 * 1024 * 1024
CAP = 1_000_000_000
BASELINE_FILE = 'baseline/original.ndjson.gz'
BASELINE_SHA256 = '5816235d98fd2e8735c5d08acc19932b2bf388e35a63032d52a322857c9b95f9'


def load_baseline():
    data = gzip.decompress((ROOT / BASELINE_FILE).read_bytes())
    if hashlib.sha256(data).hexdigest() != BASELINE_SHA256:
        raise ValueError('Original baseline checksum mismatch; published files unchanged')
    return parse(data)


def integer(value, fallback, low, high):
    if type(value) not in (int, float) or not math.isfinite(value):
        return fallback
    return min(high, max(low, math.floor(value)))


def parse(data):
    if data[:2] == b'\x1f\x8b':
        with gzip.GzipFile(fileobj=io.BytesIO(data)) as stream:
            data = stream.read(MAX_DECOMPRESSED + 1)
    if len(data) > MAX_DECOMPRESSED:
        raise ValueError('Decompressed source exceeds size limit')
    lines = [line for line in data.decode('utf-8').splitlines() if line.strip()]
    if not lines:
        raise ValueError('Empty source')
    header = json.loads(lines[0])
    if not isinstance(header, dict) or not (header.get('blocklist') == 1 or header.get('warden') == 1):
        raise ValueError('Missing native or Warden v1 header')
    rows = []
    ceiling = int(time.time()) + 86400
    for number, line in enumerate(lines[1:], 2):
        obj = json.loads(line)
        if not isinstance(obj, dict):
            raise ValueError(f'Line {number}: expected an object')
        native = 'k' in obj
        key = obj.get('k') if native else obj.get('fp')
        verdict = obj.get('v') if native else 'dead'
        if not isinstance(key, str) or not update.KEY.fullmatch(key):
            raise ValueError(f'Line {number}: invalid key')
        if not native and not key.startswith('wd1:'):
            raise ValueError(f'Line {number}: non-Warden fingerprint')
        if not isinstance(verdict, str) or verdict not in SEVERITY:
            raise ValueError(f'Line {number}: invalid verdict')
        hosts = obj.get('bk', [])
        if not isinstance(hosts, list) or any(not isinstance(host, str) for host in hosts):
            raise ValueError(f'Line {number}: invalid provider scope')
        hosts = sorted({host.strip().lower() for host in hosts if host.strip()})
        rows.append({'k': key, 'v': verdict,
                     'n': integer(obj.get('n'), 1, 1, CAP),
                     'at': integer(obj.get('at' if native else 'deadAt'), 0, 0, ceiling),
                     'bk': hosts})
    if not rows:
        raise ValueError('Source has no records; refusing to interpret it as a deletion')
    return rows


def fetch(url):
    if not url.startswith('https://'):
        raise ValueError('Source URLs must use HTTPS')
    for attempt in range(3):
        try:
            request = urllib.request.Request(url, headers={'User-Agent': 'thetoadsage-aiostreams-blocklist'})
            with urllib.request.urlopen(request, timeout=45) as response:
                data = response.read(MAX_DOWNLOAD + 1)
            if len(data) > MAX_DOWNLOAD:
                raise ValueError('Source exceeds download size limit')
            rows = parse(data)
            print(f'{len(rows):,} records: {url}', flush=True)
            return rows
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)


def merge(groups):
    by_key = {}
    for rows in groups:
        for row in rows:
            key = row['k']
            if key not in by_key:
                by_key[key] = {**row, 'bk': list(row['bk'])}
                continue
            old = by_key[key]
            if SEVERITY[row['v']] > SEVERITY[old['v']]:
                old['v'] = row['v']
            old['n'] = min(CAP, old['n'] + row['n'])
            old['at'] = max(old['at'], row['at'])
            # AIOStreams treats absent/empty scope as applying everywhere.
            old['bk'] = sorted(set(old['bk']) | set(row['bk'])) if old['bk'] and row['bk'] else []
    return [by_key[key] for key in sorted(by_key)]


def serialize(records):
    if not records:
        raise ValueError('Refusing to publish an empty aggregate')
    header = {'blocklist': 1, 'updated': max(row['at'] for row in records)}
    rows = [{k: v for k, v in row.items() if k != 'bk' or v} for row in records]
    return ('\n'.join(json.dumps(row, separators=(',', ':')) for row in [header, *rows]) + '\n').encode()


def with_baseline(baseline, current):
    records = merge([baseline, current])
    # The baseline already aggregates historical upstream observations. Adding
    # its counts to current upstream counts would count overlapping evidence twice.
    counts = {}
    for row in [*baseline, *current]:
        counts[row['k']] = max(counts.get(row['k'], 0), row['n'])
    for row in records:
        row['n'] = counts[row['k']]
    return records


def main():
    baseline = load_baseline()
    urls = json.loads((ROOT / 'sources.json').read_text())
    if not isinstance(urls, list) or not urls or any(not isinstance(url, str) for url in urls):
        raise ValueError('Expected a nonempty list of source URLs')
    if len(urls) != len(set(urls)):
        raise ValueError('Duplicate source URL')
    groups = []
    errors = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(fetch, url) for url in urls]
        for url, future in zip(urls, futures):
            try:
                groups.append(future.result())
            except Exception as error:
                errors.append(f'{url}: {error}')
    if errors:
        raise RuntimeError('Published files unchanged; failed sources:\n' + '\n'.join(errors))
    records = with_baseline(baseline, merge(groups))
    with tempfile.TemporaryDirectory() as directory:
        export = Path(directory) / 'aggregate.ndjson'
        export.write_bytes(serialize(records))
        files, manifest = update.prepare(export)
    manifest['aggregation'] = {
        'mode': 'baseline-plus-mirror', 'source_count': len(urls), 'sources': urls,
        'baseline': {'file': BASELINE_FILE, 'entries': len(baseline), 'sha256': BASELINE_SHA256},
    }
    # No published files are touched until every source and the result validate.
    for name, body in files.items():
        (ROOT / name).write_bytes(body)
    (ROOT / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(f'Published {len(records):,} unique keys from {len(urls)} sources')


if __name__ == '__main__':
    main()
