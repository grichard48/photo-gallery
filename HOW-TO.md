# Photo Gallery — How It Works & How to Use It

A plain-language reference for the gallery at **www.winterfarm.ca**.

## What the system is

- **Your photos** live on your Mac / NAS in the `photos/` folder. Each folder
  becomes an album; nested folders become nested albums.
- **Resized copies** (a web-size image + a thumbnail of every photo) live in a
  **Cloudflare R2** bucket called `photo-gallery`. Originals are never uploaded,
  and location/EXIF data is stripped from the published copies.
- **The website** is a small Cloudflare Worker that serves the page and streams
  images from R2. Your git repo only holds code + a small index file
  (`manifest.json`) — never the photos — so it stays tiny.

## Adding photos (the routine)

1. **Drop photos** into `photos/` — into existing folders like
   `photos/Photos/Farm/2026/August/`, or make new folders as needed. Folder
   names become album titles.
2. **Upload them.** In Terminal:
   ```
   cd ~/Programming/photo-gallery
   ./scripts/publish.sh
   ```
   This resizes and uploads only the *new* photos to R2 (it skips anything
   already uploaded) and rebuilds the index. The first run imported ~14,000
   photos; normal runs finish in seconds.
3. **Publish.** Open **GitHub Desktop**, commit the changes, and click
   **Push origin**. Cloudflare redeploys automatically in ~2–3 minutes.

That's it: **add → `./scripts/publish.sh` → commit & push.**

## Naming & sorting

- Underscores display as spaces: `Spring_Garden` → "Spring Garden".
- Folders named after months sort in calendar order (March before April).
- Other albums sort alphabetically; photos within an album sort by date taken.

## Other tweaks

- **Gallery title:** edit `config.json`, then run the publish routine.
- **Home banner:** replace `site/banner.jpg` (a wide ~2000px image), then publish.
- **Colors:** the `:root` block near the top of `site/index.html`.

## Choosing an album's cover photo

By default an album's cover is its first photo (earliest capture date, then
filename). To pick a specific one, put a file named `.cover` in that folder
containing just the chosen image's filename, then publish. For example, to make
`_DSF2643.jpg` the cover of the August album:

```
echo "_DSF2643.jpg" > photos/Scrapbook/Seattle/2015/August/.cover
```

Notes:

- The match ignores case and extension, so `_DSF2643`, `_dsf2643.jpg`, and
  `_DSF2643.JPG` all work.
- It works at any level. A `.cover` on a container folder (like `Seattle`) may
  name any photo anywhere beneath it.
- If the named photo isn't found, the build prints a warning and falls back to
  the default cover.
- `.cover` is a hidden file and isn't treated as a photo or uploaded — it just
  guides the build. Applying it only needs a publish (no re-upload), then a push.

## Removing photos

Delete the images from `photos/` and publish as usual — they disappear from the
gallery right away. Their resized copies, though, stay in R2 (the build only ever
adds), so they linger as harmless orphans taking a little storage.

To clean those up, after publishing run:

```
python3 scripts/prune_orphans.py --dry-run   # preview what would be deleted
python3 scripts/prune_orphans.py             # delete them (asks to confirm)
```

It compares the live `dist/manifest.json` against everything in the bucket and
removes only objects nothing points at anymore. Always publish first so the
manifest reflects your deletions; the script refuses to run on an empty manifest
and warns if a prune would remove an unusually large share of the bucket.

So the full remove-and-clean flow is: delete from `photos/` -> `./scripts/publish.sh`
-> commit & push -> `python3 scripts/prune_orphans.py`.

## Renaming an album folder (important)

A folder name is baked into each image's storage address, so renaming a folder
and running publish would re-upload every photo in it. To rename **without** a
mass re-upload:

1. Rename the local folder (e.g. `photos/Photos` -> `photos/Scrapbook`).
2. `python3 scripts/rename_album.py Photos Scrapbook` — moves the images inside
   R2 (fast, server-side, no re-upload) and updates the build cache.
3. `./scripts/publish.sh` — rebuilds the index (should report `0 uploaded`).
4. Commit & push in GitHub Desktop.

To delete stray image objects from R2 (e.g. cleanup), use
`python3 scripts/prune_r2.py i/SomeName/ t/SomeName/`.

## Good to know

- **Where things live:** photos on your Mac/NAS, resized images in R2, code on
  GitHub + Cloudflare. The originals are the system of record — keep your backups.
- **Credentials:** your R2 keys are in a local `.env` file (never committed). If
  you ever move to a new computer, you'll recreate `.env` from `.env.example`
  and `pip install -r requirements.txt`.
- **Cost:** R2's free tier covers ~10 GB and free bandwidth; your library
  (~2–3 GB) sits well within it.
- **If the site doesn't update:** make sure you did all three steps — the upload
  *and* the commit & push. The push is what triggers the deploy.

## One-time setup that's already done

R2 enabled, bucket created, API token + `.env` configured, Python deps
installed, Worker deployed via the GitHub → Cloudflare integration. You won't
need to repeat these unless you switch computers. Full technical detail is in
`README.md`.
