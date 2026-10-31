# AIOStreams blocklist

An automatically updated, deduplicated aggregate of the public blocklists in [sources.json](sources.json). GitHub Actions checks the sources **every six hours**, converts native and Warden records into native AIOStreams NDJSON, and commits only changed output. No server credentials or personal access token are needed.

This is a **mirror**: entries disappear when no configured source contains them anymore. The original uploaded export remains preserved in [the initial backup commit](https://github.com/thetoadsage/aiostreams-blocklist/tree/b2961abb07578a9ce4f9a9d6499185fc01db86d6). It contained 184,074 unique keys. The current count, key types, verdicts, and SHA-256 hashes are in [manifest.json](manifest.json).

## Use in AIOStreams

In **Dashboard → Blocklists → Sources → Subscribe to a list**, enter:

```text
https://raw.githubusercontent.com/thetoadsage/aiostreams-blocklist/main/blocklist-all.ndjson.gz
```

Name it `Combined blocklist` and use **Full** trust to apply its verdicts directly. Leave the refresh interval at 24 hours, or shorten it to six hours to follow the repository more closely. Refresh the source and check its entry count after subscribing. AIOStreams automatically decompresses gzip. An uncompressed alternative is:

```text
https://raw.githubusercontent.com/thetoadsage/aiostreams-blocklist/main/blocklist-all.ndjson
```

For a one-time restore, download [blocklist-all.ndjson.gz](blocklist-all.ndjson.gz) and use the Blocklists import option. Imports become a separate source; they do not merge into AIOStreams' local source.

This aggregate is not independent corroborating evidence. Subscribing to it and its original sources must not count as independent confirmations. Provider scope is preserved, including entries with no scope, which AIOStreams treats as applicable everywhere. Native format retains `nh1:` post hashes as well as `wd1:` fingerprints.

## Automatic updates

The [Update blocklist workflow](https://github.com/thetoadsage/aiostreams-blocklist/actions/workflows/update.yml) runs at minute 23 every six hours in UTC, on relevant source/code changes, and through **Run workflow**. GitHub schedules are best effort and can be delayed; scheduled workflows in public repositories can be disabled after 60 days without repository activity. See [GitHub scheduling documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

Each run:

1. Downloads every enabled source, retrying failures, with size and timeout limits.
2. Validates every source. Empty, malformed, or unavailable sources **fail the entire update**, leaving the published list unchanged. Check failed runs on the Actions page; a persistently unavailable source must be repaired or deliberately removed from `sources.json`.
3. Rebuilds the aggregate from current sources, without feeding the previous aggregate back into itself. Following AIOStreams' deduplication rules, repeated keys use the strongest verdict, newest observation timestamp, capped sum of observation counts, and combined provider scopes. An unrestricted scope overrides narrower scopes. Counts are not independent-source trust votes.
4. Validates the result, creates a compressed copy and integrity manifest, and commits only if files changed.

There are 30 enabled sources initially. Three supplied URLs returned HTTP 404 during setup and are recorded in [disabled-sources.json](disabled-sources.json): `mattskiiau`, `0-nj`, and `Febsho`. They are not fetched automatically; add working replacement URLs to `sources.json` to enable them. The escaped URLs from the supplied list were cleaned up, and the `chrs-alt-esc` and `fourpoint8` Gist URLs now follow the latest revision instead of fixed historical revisions.

Edit `sources.json` to add or remove public source URLs. Never add this repository's own feed: that would preserve removed entries and inflate observation counts. If you fork this repository, also change its subscription URL in this README.

This job reads only the configured public sources. It does **not** connect to your AIOStreams instance or automatically capture your own new local verdicts. To include those, publish a **Local / native** Gist from AIOStreams' Blocklists → Publishing page, then add that Gist's latest raw URL to `sources.json`. Publish Local, rather than All, to avoid feeding this aggregate back into itself.

## Run locally

Requires Python 3 with no additional packages:

```sh
python3 -m unittest discover -s tests -v
python3 scripts/aggregate.py
git diff --stat
git add blocklist-all.ndjson blocklist-all.ndjson.gz manifest.json
git commit -m "Update aggregated blocklist"
git push
```

`scripts/update.py /path/to/blocklist-all.ndjson` remains available to validate and copy a manually exported native snapshot. The next automatic run replaces that snapshot with the current configured-source aggregate.

## Original backup and integrity

The original October 31, 2026 upload is available unchanged at:

- [Original native export](https://raw.githubusercontent.com/thetoadsage/aiostreams-blocklist/b2961abb07578a9ce4f9a9d6499185fc01db86d6/blocklist-all.ndjson)
- [Original compressed export](https://raw.githubusercontent.com/thetoadsage/aiostreams-blocklist/b2961abb07578a9ce4f9a9d6499185fc01db86d6/blocklist-all.ndjson.gz)

Original NDJSON SHA-256: `5816235d98fd2e8735c5d08acc19932b2bf388e35a63032d52a322857c9b95f9`.

The published records contain hashed release identities, verdicts, counts, timestamps, and provider hosts, not release titles, download URLs, account credentials, or API keys. To verify a downloaded file, compare its SHA-256 with `manifest.json`, for example with `shasum -a 256 blocklist-all.ndjson.gz`. These checks detect changed bytes; they are not a cryptographic signature.

See the [AIOStreams release blocklist guide](https://docs.aiostreams.viren070.me/guides/release-blocklist/) for trust, provider scope, importing, and publishing behavior.
