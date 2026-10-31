#!/usr/bin/env python3
"""Validate a native AIOStreams export and refresh the published snapshot."""
import argparse
import collections
import gzip
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
KEY = re.compile(r"(?:wd1:[0-9a-f]{32}|nh1:[0-9a-f]{40}|btih:(?:[0-9a-f]{40}|[0-9a-f]{64}))")


def prepare(source):
    data = source.read_bytes()
    rows = [json.loads(line) for line in data.decode('utf-8').splitlines() if line.strip()]
    if not rows or not isinstance(rows[0], dict) or rows[0].get('blocklist') != 1:
        raise ValueError('Expected a native AIOStreams blocklist:1 header')
    if set(rows[0]) != {'blocklist', 'updated'}:
        raise ValueError('Unexpected header fields; review before publishing')
    seen = set()
    kinds, verdicts = collections.Counter(), collections.Counter()
    for number, row in enumerate(rows[1:], 2):
        if not isinstance(row, dict) or not {'k', 'v', 'n', 'at'} <= row.keys():
            raise ValueError(f'Incomplete record on line {number}')
        if set(row) - {'k', 'v', 'n', 'at', 'bk'}:
            raise ValueError(f'Unexpected fields on line {number}; review before publishing')
        key = row['k']
        if not isinstance(key, str) or not KEY.fullmatch(key):
            raise ValueError(f'Invalid release key on line {number}')
        if key in seen:
            raise ValueError(f'Duplicate key on line {number}; export deduplicated scope All')
        if row['v'] not in {'dead', 'defective', 'fake', 'mislabeled'}:
            raise ValueError(f'Invalid verdict on line {number}')
        if type(row['n']) is not int or not 1 <= row['n'] <= 1_000_000_000:
            raise ValueError(f'Invalid count on line {number}')
        if type(row['at']) is not int or row['at'] < 0:
            raise ValueError(f'Invalid timestamp on line {number}')
        if 'bk' in row and (not isinstance(row['bk'], list) or any(
            not isinstance(host, str) or not re.fullmatch(r'[a-zA-Z0-9.-]+', host)
            for host in row['bk']
        )):
            raise ValueError(f'Invalid provider hostname on line {number}')
        seen.add(key)
        kinds[key.split(':', 1)[0]] += 1
        verdicts[row['v']] += 1
    if not seen:
        raise ValueError('Refusing to publish an empty blocklist')
    files = {'blocklist-all.ndjson': data, 'blocklist-all.ndjson.gz': gzip.compress(data, mtime=0)}
    manifest = {
        'format': 'AIOStreams native NDJSON v1',
        'scope': 'all',
        'header_updated': rows[0]['updated'],
        'entries': len(seen),
        'key_types': dict(sorted(kinds.items())),
        'verdicts': dict(sorted(verdicts.items())),
        'files': {name: {'bytes': len(body), 'sha256': hashlib.sha256(body).hexdigest()}
                  for name, body in files.items()},
    }
    return files, manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('export', type=Path, help='Fresh native NDJSON export (scope All)')
    args = parser.parse_args()
    files, manifest = prepare(args.export)
    # All validation finishes before replacing any published files.
    for name, body in files.items():
        (ROOT / name).write_bytes(body)
    (ROOT / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(f"Validated and saved {manifest['entries']:,} unique entries")


if __name__ == '__main__':
    main()
