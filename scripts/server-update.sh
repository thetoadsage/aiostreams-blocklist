#!/usr/bin/env bash
# Installed outside the checkout; each run uses a fresh, disposable worktree.
set -euo pipefail

app_dir="${1:?Usage: server-update.sh /absolute/application/directory}"
repository="$app_dir/repository.git"
checkout_dir=""
outcome="failed"
published_commit=""
started_at="$(date -u +%FT%TZ)"
stage="setup"

mkdir -p "$app_dir/runs"
exec 9>"$app_dir/update.lock"
if ! flock -n 9; then
    echo 'Another blocklist update is already running; skipping.'
    exit 0
fi

finish() {
    result=$?
    trap - EXIT
    set +e
    cd "$app_dir"
    if [[ -n "$checkout_dir" ]]; then
        git --git-dir="$repository" worktree remove --force "$checkout_dir" || true
        if [[ -d "$checkout_dir" ]]; then rmdir "$checkout_dir" || true; fi
    fi
    python3 "$app_dir/health.py" "$app_dir" record \
        "$result" "$outcome" "$published_commit" "$started_at" "$stage"
    if [[ $? -ne 0 ]]; then
        echo 'Failed to record updater health.' >&2
        if [[ "$result" -eq 0 ]]; then result=1; fi
    fi
    echo "Blocklist update finished: exit=$result outcome=$outcome stage=$stage"
    exit "$result"
}
trap finish EXIT
trap 'exit 143' TERM
trap 'exit 130' INT

echo "Starting blocklist update at $(date -u +%FT%TZ)"
stage="fetch"
git --git-dir="$repository" fetch --prune origin '+refs/heads/main:refs/remotes/origin/main'
checkout_dir="$(mktemp -d "$app_dir/runs/run.XXXXXX")"
git --git-dir="$repository" worktree add --detach "$checkout_dir" refs/remotes/origin/main
cd "$checkout_dir"

stage="tests"
python3 -m unittest discover -s tests -v
stage="aggregate"
python3 scripts/aggregate.py
stage="commit"
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
    stage="push"
    git push origin HEAD:refs/heads/main
    outcome="updated"
fi
published_commit="$(git rev-parse HEAD)"
stage="complete"
