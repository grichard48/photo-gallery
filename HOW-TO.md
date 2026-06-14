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
