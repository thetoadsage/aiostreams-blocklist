# AIOStreams blocklist

A combined blocklist that keeps all **184,074 original entries** and adds blocks from community sources. Duplicates are removed automatically.

## Add to AIOStreams

Go to **Dashboard → Blocklists → Sources → Subscribe to a list** and paste:

```text
https://raw.githubusercontent.com/thetoadsage/aiostreams-blocklist/main/blocklist-all.ndjson.gz
```

Choose **Full** trust and a **6-hour** refresh interval.

## Updates

- Checks [community sources](sources.json) every six hours.
- Always keeps the original entries. Later additions follow the current sources.
- Keeps the last working list if an update fails.

[Update status](https://github.com/thetoadsage/aiostreams-blocklist/actions/workflows/update.yml) · [Current entry count](manifest.json) · [Unavailable sources](disabled-sources.json)

## Backup

[Download the current list](blocklist-all.ndjson.gz) or the [original export](baseline/original.ndjson.gz) to import manually in AIOStreams.
