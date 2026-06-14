# Photo Gallery

A photo gallery backed by Cloudflare R2 object storage. Folders inside `photos/`
become albums (nesting supported). Resized images live in an R2 bucket — there's
no limit on how many photos you can have, and your git repo stays tiny.

## How it works

```
photo-gallery/
├── photos/            ← your photos, organized in folders (NOT committed to git)
│   └── Photos/
│       ├── Farm/2007/December/
│       ├── Seattle/2026/March/
│       └── Travels/07Barcelona/
├── config.json        ← gallery title
├── site/index.html    ← the gallery web page
├── site/banner.jpg    ← home page banner image (optional)
├── scripts/build.py   ← resizes photos, uploads them to R2, writes manifest.json
├── scripts/worker.js  ← serves images from R2; serves the site shell
├── scripts/publish.sh ← one command: build (upload) + deploy
├── wrangler.jsonc     ← Cloudflare Worker + R2 config
├── .env               ← your R2 credentials (NOT committed — see .env.example)
└── requirements.txt
```

`build.py` makes two resized copies of each photo — a web-size image and a
thumbnail — and uploads them to the R2 bucket. Originals are never uploaded, and
EXIF metadata (including GPS location) is stripped from the published copies. It
also writes `dist/manifest.json`, the small index the page uses for navigation.
The Worker (`worker.js`) streams images from R2 at `/i/<...>` (web) and
`/t/<...>` (thumbnails) with edge caching, and serves the static shell
(`index.html`, `manifest.json`, `banner.jpg`) for everything else.

Folder names become album titles; underscores display as spaces (`Spring_Garden`
→ "Spring Garden"). Photos sort by capture date (from EXIF, falling back to
filename); albums sort alphabetically, except folders named after months, which
sort chronologically (March before April before May).

## Publishing (adding photos, changing the title, etc.)

Two steps — upload the images, then push to deploy:

```bash
./scripts/publish.sh                  # resize + upload new/changed photos to R2
```

Then open **GitHub Desktop**, commit the changes, and click **Push origin**.
Cloudflare redeploys automatically (~2–3 min). No Node or wrangler needed on your
Mac — the push triggers the deploy.

The upload is incremental — a local `.build-cache.json` records what's already
been uploaded, so re-runs only process new photos and finish quickly.

Day-to-day flow:

1. Drop photos into `photos/<album>/` (create folders freely — they become albums).
2. Run `./scripts/publish.sh`.
3. Commit & push in GitHub Desktop. That push is what triggers the deploy.

The originals on your Mac / NAS are the system of record; git holds the code and
the manifest (a small index file), never the photos themselves.

## First-time setup (already completed)

The R2 bucket, credentials, and deploy pipeline are configured. For reference,
the one-time steps were:

1. **Enable R2** in the Cloudflare dashboard (requires a payment method on file,
   but typical usage sits in the free tier).
2. **Create the bucket** named `photo-gallery` (R2 → Create bucket).
3. **Create R2 API credentials** (R2 → *Manage R2 API Tokens* → *Create API
   Token* → Object Read & Write) and put them in a local `.env` (see
   `.env.example`).
4. **Install Python deps:** `pip install -r requirements.txt`.

Deployment runs through the existing GitHub → Cloudflare Workers integration:
every push runs the build — which, when no credentials are present, simply
re-deploys the committed shell — followed by `wrangler deploy`. No local Node or
wrangler is required. The `wrangler.jsonc` `"name"` and `bucket_name` are both
`photo-gallery`.

## Customizing

- **Gallery title:** edit `config.json`, then publish.
- **Home page banner:** replace `site/banner.jpg` (a wide crop, ~2000px across,
  works best). Delete it to remove the banner — the page handles its absence.
- **Colors:** CSS variables in the `:root` block at the top of `site/index.html`.
- **Image sizes/quality:** constants at the top of `scripts/build.py`
  (`THUMB_WIDTH`, `WEB_MAX_EDGE`, quality settings). Changing these and
  re-publishing won't re-upload existing photos unless you delete
  `.build-cache.json` first (which forces a full re-process).

## Previewing locally (optional)

`build.py` uploads to R2 and writes `dist/manifest.json`. To preview the built
shell locally after a publish:

```bash
cd dist && python3 -m http.server 8000   # then open http://localhost:8000
```

Note that images load from R2, so a local preview still pulls them from the live
bucket.

## Limits worth knowing

- **R2 free tier:** 10 GB storage, 1M writes/month, 10M reads/month, and — the
  headline — **free egress** (no bandwidth charges). ~14,000 photos is roughly
  2–3 GB, well inside the free tier. Beyond 10 GB, storage is about
  $0.015/GB-month.
- **No file-count ceiling.** Unlike static-asset hosting, R2 imposes no
  20,000-file limit, so you can keep both full web images and thumbnails for as
  many photos as you like.
- **Deleted photos:** removing a file from `photos/` drops it from the manifest,
  but its objects remain in R2 (harmless orphans). Periodic cleanup can be added
  if needed.

## Supported formats

JPEG, PNG, WebP, TIFF, BMP. Everything is published as JPEG. Files and folders
starting with `.` are ignored.
