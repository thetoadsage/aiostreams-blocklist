#!/usr/bin/env bash
# Installed outside the checkout; each run uses a fresh, disposable worktree.
set -euo pipefail

app_dir="${1:?Usage: server-update.sh /absolute/application/directory}"
repository="$app_dir/repository.git"
checkout_dir=""
outcome="failed"
published_commit=""

mkdir -p "$app_dir/runs"
exec 9>"$app_dir/update.lock"
if ! flock -n 9; then
    echo 'Another blocklist update is already running; skipping.'
    exit 0
fi

finish() {
    result=$?
    trap - EXIT
    cd "$app_dir"
    if [[ -n "$checkout_dir" ]]; then
        git --git-dir="$repository" worktree remove --force "$checkout_dir" || true
        if [[ -d "$checkout_dir" ]]; then rmdir "$checkout_dir" || true; fi
    fi
    python3 - "$app_dir/last-run.json" "$result" "$outcome" "$published_commit" <<'PY'
import datetime
import json
from pathlib import Path
import sys

path, code, outcome, commit = sys.argv[1:]
state = {
    'finished_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'exit_code': int(code),
    'outcome': outcome if code == '0' else 'failed',
    'commit': commit or None,
}
temporary = Path(path + '.tmp')
temporary.write_text(json.dumps(state, indent=2) + '\n')
temporary.replace(path)
PY
    echo "Blocklist update finished: exit=$result outcome=$outcome"
    exit "$result"
}
trap finish EXIT

echo "Starting blocklist update at $(date -u +%FT%TZ)"
git --git-dir="$repository" fetch --prune origin '+refs/heads/main:refs/remotes/origin/main'
checkout_dir="$(mktemp -d "$app_dir/runs/run.XXXXXX")"
git --git-dir="$repository" worktree add --detach "$checkout_dir" refs/remotes/origin/main
cd "$checkout_dir"

python3 -m unittest discover -s tests -v
python3 scripts/aggregate.py
git add blocklist-all.ndjson blocklist-all.ndjson.gz manifest.json

if git diff --cached --quiet; then
    outcome="unchanged"
    echo 'Blocklist unchanged.'
else
    git -c user.name='AIOStreams blocklist updater' \
        -c user.email='33288669+thetoadsage@users.noreply.github.com' \
        commit -m 'Update aggregated blocklist'
    # A non-fast-forward rejection preserves newer remote changes. The service
    # retries later from a fresh fetch instead of overwriting them.
    git push origin HEAD:refs/heads/main
    outcome="updated"
fi
published_commit="$(git rev-parse HEAD)"
