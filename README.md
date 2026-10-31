# AIOStreams blocklist

A community blocklist with **190,000+ unique items**, updated automatically every six hours.

## Add to AIOStreams

1. Open the AIOStreams **Dashboard → Blocklists → Sources**, then click **Subscribe to a list**.

   ![Open Blocklists in the sidebar and click Subscribe to a list](docs/images/blocklists-sources.png)

2. Paste this address into **List URL(s)**:

   ```text
   https://raw.githubusercontent.com/thetoadsage/aiostreams-blocklist/main/blocklist-all.ndjson.gz
   ```

3. Set **Trust** to **full** and **Refresh (hours)** to **6**, then click **Subscribe**.

   ![Subscription dialog with the list URL, full trust and a six-hour refresh interval](docs/images/subscribe-to-blocklist.png)

## Contribute your own blocks

Publish your instance's own blocks to a GitHub Gist so they can be included here.

1. [Create a fine-grained GitHub token](https://github.com/settings/personal-access-tokens/new). Name it `AIOStreams blocklist`, choose your personal account as **Resource owner**, and set an expiration. Under **Account permissions**, grant **Gists → Read and write**, then generate and copy the token. No repository permissions are needed. Keep the token private and replace it in AIOStreams before it expires. [GitHub token guide](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens#creating-a-fine-grained-personal-access-token).
2. In **Dashboard → Blocklists → Publishing**, click **Add target** and choose **GitHub Gist**.
3. Enter a name, set the push interval to **6 hours**, and paste your token. Leave **Gist ID** blank. Under **Files to push**, choose **native** format and **local (own verdicts)** scope. Use local so you contribute your own blocks without republishing subscribed lists.
4. Click **Add target**, then the target's **Push now** upload button. Once it succeeds, click the copy icon beside `blocklist-local.ndjson` to copy its shareable URL. AIOStreams will keep the Gist updated on your chosen interval. Public visibility is optional; secret Gists also work, and anyone with their URL can read them.
5. [Open an issue](https://github.com/thetoadsage/aiostreams-blocklist/issues/new) with that URL, or submit a pull request adding it to [sources.json](sources.json). Share the list URL only, never your token.

<details>
<summary>See the publishing screens</summary>

Open Publishing and click **Add target**:

![Blocklist Publishing page with Add target and the Publishing sidebar icon highlighted](docs/images/blocklist-publishing.png)

Set up a GitHub Gist target with **native** format and **local (own verdicts)** scope:

<img src="docs/images/add-publish-target.png" width="500" alt="Add publish target form with GitHub Gist, a six-hour interval, a blank token and Gist ID, native format and local scope">

</details>

## Updates

- Checks [community sources](sources.json) every six hours.
- Always keeps the original entries. Later additions follow the current sources.
- Keeps the last working list if an update fails.

[Update status](https://github.com/thetoadsage/aiostreams-blocklist/actions/workflows/update.yml) · [Current entry count](manifest.json) · [Unavailable sources](disabled-sources.json)

## Backup

[Download the current list](blocklist-all.ndjson.gz) or the [original export](baseline/original.ndjson.gz) to import manually in AIOStreams.
