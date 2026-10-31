# AIOStreams blocklist

Personal backup of an AIOStreams **All** export, preserved in the native NDJSON format. This is an aggregate snapshot: it may include subscribed lists as well as locally recorded verdicts. It is not an independent source of corroborating evidence.

Initial snapshot saved October 31, 2026: **184,074 unique release keys**, with no duplicates. There are 178,154 `wd1:` keys and 5,920 `nh1:` keys, all marked `dead`. Key counts are not a count of distinct releases: one release can have both identities. Current counts and SHA-256 hashes are in [manifest.json](manifest.json).

## Use in AIOStreams

In **Dashboard → Blocklists → Sources → Subscribe to a list**, enter this URL:

```text
https://raw.githubusercontent.com/thetoadsage/aiostreams-blocklist/main/blocklist-all.ndjson.gz
```

Name it `Personal blocklist backup`, use **Full** trust if you want to apply your saved verdicts directly, and leave the refresh interval at 24 hours. Refresh the source and check its entry count after subscribing. AIOStreams automatically decompresses gzip; an uncompressed alternative is:

```text
https://raw.githubusercontent.com/thetoadsage/aiostreams-blocklist/main/blocklist-all.ndjson
```

For a one-time restore, download [blocklist-all.ndjson.gz](blocklist-all.ndjson.gz) and use the Blocklists import option. Imports become a separate source; they do not merge into AIOStreams' local source.

Provider scope is preserved. AIOStreams applies its configured backbone matching rules, so a saved `dead` verdict does not necessarily apply to every provider. There are 324 entries in the initial snapshot with no recorded provider scope; AIOStreams treats those as applicable everywhere.

## Keep the backup current

This repository is a snapshot, not an automatic connection to your server. AIOStreams subscription refreshes only pick up changes committed here.

1. Export **native NDJSON**, scope **All**, from AIOStreams.
2. In a local checkout of this repository, run:

   ```sh
   python3 scripts/update.py /path/to/blocklist-all.ndjson
   git diff --stat
   git add blocklist-all.ndjson blocklist-all.ndjson.gz manifest.json
   git commit -m "Update blocklist snapshot"
   git push
   ```

The helper validates the export, rejects duplicate keys and unexpected fields, preserves the original NDJSON bytes, and regenerates the compressed copy and integrity manifest. It requires Python 3 and no additional packages. Git history retains earlier snapshots.

When exporting All after subscribing to this backup, remember that the backup itself is now a source: removed upstream verdicts can remain present through that subscription, and observation counts can accumulate. For a clean replacement snapshot, export from an instance that is not subscribed to this backup. Disabling the subscription alone is insufficient in versions that export entries from disabled sources too.

For automatic publishing, AIOStreams currently supports **GitHub Gist** targets under Blocklists → Publishing. That is a separate destination; setting up this repository does not enable automatic publishing.

## Sharing and integrity

The export contains hashed release identities, verdicts, observation counts, timestamps, and provider hostnames. It contains no release titles, download URLs, account credentials, or API keys. Provider hostnames remain visible because they affect whether a verdict should apply.

Because this is an All-scope aggregate, do not treat it and its upstream sources as independent corroborating votes. Native NDJSON preserves `nh1:` keys, which would be lost in a Warden-only conversion.

To verify a downloaded file, compare its SHA-256 with `manifest.json`, for example with `shasum -a 256 blocklist-all.ndjson.gz`. These checks detect changed bytes; they are not a cryptographic signature.

See the official [AIOStreams release blocklist guide](https://docs.aiostreams.viren070.me/guides/release-blocklist/) for trust, provider scope, importing, and publishing behavior.
