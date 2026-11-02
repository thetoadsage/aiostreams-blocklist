# Server updater

The updater runs on the owner's server as the `devon` user's systemd service. GitHub hosts the feed; GitHub Actions does not run updates.

## Installed layout

- `/opt/docker/apps/aiostreams-blocklist/run-update.sh` — installed copy of `scripts/server-update.sh`.
- `repository.git/` — dedicated bare clone of this repository.
- `runs/` — temporary worktrees, removed after each run.
- `update.lock` — prevents overlapping runs.
- `last-run.json` — latest completion time, outcome and published commit.
- `~/.config/systemd/user/aiostreams-blocklist.{service,timer}` — copies of the units in this directory.
- `~/.ssh/aiostreams_blocklist_deploy` — private, repository-specific GitHub deploy key. Keep this outside the repository and back it up securely.

Each run fetches current `main`, runs the unit tests and aggregation in a fresh worktree, and pushes changed output without force. Unchanged output creates no commit. A concurrent upstream change rejects the push instead of overwriting it; a later retry starts fresh. Code, sources and baseline are fetched on every run; changes to the installed runner or units require reinstalling those files.

The timer runs at **00:23, 06:23, 12:23 and 18:23 UTC**, with one-second timer accuracy and no added random delay. `Persistent=true` catches up once after downtime. Failures are logged and retried after 15 minutes. The user's existing `Linger=yes` setting keeps the service manager running without an interactive login and starts it at boot. This is a user service, not a Docker container.

## Check or run it

As the service user on the server:

```sh
systemctl --user list-timers aiostreams-blocklist.timer
systemctl --user status aiostreams-blocklist.service
journalctl --user -u aiostreams-blocklist.service -n 60 --no-pager
cat /opt/docker/apps/aiostreams-blocklist/last-run.json
systemctl --user start aiostreams-blocklist.service
```

A completed oneshot service normally shows `inactive (dead)` with `Result=success`. The timer should remain `active (waiting)`.

To pause updates:

```sh
systemctl --user stop aiostreams-blocklist.timer aiostreams-blocklist.service
```

To resume:

```sh
systemctl --user enable --now aiostreams-blocklist.timer
```

The existing subscription URL is unchanged. No inbound server access or GitHub personal access token is required. The deploy key has write access only to this repository.
