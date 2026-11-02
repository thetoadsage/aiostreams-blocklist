#!/usr/bin/env python3
"""Record update outcomes and report failed or overdue updates to the journal."""
import argparse
import datetime
import json
from pathlib import Path
import sys

UTC = datetime.timezone.utc
SUCCESS = {'updated', 'unchanged'}


def read_state(path):
    state = json.loads(path.read_text())
    if not isinstance(state, dict):
        raise ValueError('Expected an update state object')
    return state


def last_success(state):
    # Accept the original state format during the deployment upgrade.
    if state.get('last_success_at'):
        return state['last_success_at'], state.get('last_success_commit')
    if state.get('exit_code') == 0 and state.get('outcome') in SUCCESS:
        return state.get('finished_at'), state.get('commit')
    return None, None


def record(app_dir, code, outcome, commit, started_at, stage, now=None):
    path = app_dir / 'last-run.json'
    try:
        previous = read_state(path)
    except (OSError, ValueError):
        previous = {}
    success_at, success_commit = last_success(previous)
    finished = (now or datetime.datetime.now(UTC)).isoformat()
    succeeded = code == 0 and outcome in SUCCESS
    failures = previous.get('consecutive_failures', 0)
    if type(failures) is not int or failures < 0:
        failures = 0
    state = {
        'started_at': started_at, 'finished_at': finished,
        'exit_code': code, 'outcome': outcome if succeeded else 'failed',
        'stage': stage, 'commit': commit or None,
        'last_success_at': finished if succeeded else success_at,
        'last_success_commit': commit if succeeded else success_commit,
        'consecutive_failures': 0 if succeeded else failures + 1,
    }
    temporary = path.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(state, indent=2) + '\n')
    temporary.replace(path)


def check(app_dir, max_age_hours=8, now=None):
    try:
        state = read_state(app_dir / 'last-run.json')
        success_at, _ = last_success(state)
        if state.get('exit_code') != 0 or state.get('outcome') not in SUCCESS:
            return False, f"Update failed at stage {state.get('stage', 'unknown')}; inspect aiostreams-blocklist.service journal"
        if not success_at:
            return False, 'No successful update recorded'
        timestamp = datetime.datetime.fromisoformat(success_at)
        if timestamp.tzinfo is None:
            raise ValueError('Success timestamp needs a timezone')
        age = ((now or datetime.datetime.now(UTC)) - timestamp).total_seconds()
        if age < -300:
            return False, 'Success timestamp is in the future; check server clock'
        if age > max_age_hours * 3600:
            return False, f'Update overdue: last success {success_at} (limit {max_age_hours:g}h)'
        return True, f"Update healthy: {state['outcome']}, last success {success_at}"
    except (OSError, ValueError, TypeError) as error:
        return False, f'Cannot verify update health: {error}'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('app_dir', type=Path)
    commands = parser.add_subparsers(dest='command', required=True)
    recording = commands.add_parser('record')
    recording.add_argument('code', type=int)
    recording.add_argument('outcome')
    recording.add_argument('commit')
    recording.add_argument('started_at')
    recording.add_argument('stage')
    checking = commands.add_parser('check')
    checking.add_argument('--max-age-hours', type=float, default=8)
    args = parser.parse_args()
    if args.command == 'record':
        record(args.app_dir, args.code, args.outcome, args.commit, args.started_at, args.stage)
    else:
        if not 0 < args.max_age_hours < float('inf'):
            parser.error('--max-age-hours must be positive and finite')
        healthy, message = check(args.app_dir, args.max_age_hours)
        print(message, file=sys.stdout if healthy else sys.stderr)
        return 0 if healthy else 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
