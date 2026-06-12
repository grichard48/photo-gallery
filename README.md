# Photo Gallery

A simple static photo gallery. Folders inside `photos/` become albums (nesting supported). Push to GitHub, and Cloudflare Pages rebuilds and deploys automatically.

## How it works

```
photo-gallery/
├── photos/            ← your photos, organized in folders (this is all you touch)
│   ├── 2025/
│   │   └── Spring_Garden/
│   └── Family/
├── config.json        ← gallery title
├── site/index.html    ← the gallery web page
├── scripts/build.py   ← generates thumbnails + web-size images into dist/
└── requirements.txt
```

On every push, Cloudflare runs `build.py`, which creates resized copies of each photo (originals are never published, and EXIF metadata — including GPS location — is stripped from the published copies) plus a `manifest.json` the page uses for navigation.

Folder names become album titles; underscores display as spaces (`Spring_Garden` → "Spring Garden"). Photos sort by capture date (from EXIF, falling back to filename); albums sort alphabetically, except folders named after months, which sort chronologically (March before April before May).

## One-time setup (~10 minutes)

### 1. Put this folder on GitHub

Easiest path if you don't use git locally:

1. On github.com: **New repository** → name it (e.g. `photo-gallery`), Private is fine → Create.
2. On the new repo page: **uploading an existing file** link (or Add file → Upload files).
3. Drag the *contents* of this folder (not the folder itself) into the upload area — folders drag in with their structure intact. Commit.

If you use GitHub Desktop or the command line, just init/commit/push as usual. `dist/` is gitignored — it's generated, never committed.

### 2. Connect Cloudflare Pages

1. Sign up / log in at [dash.cloudflare.com](https://dash.cloudflare.com) (free plan).
2. **Workers & Pages → Create → Pages → Connect to Git** → authorize GitHub → pick your repo.
3. Build settings:
   - **Framework preset:** None
   - **Build command:** `pip install -r requirements.txt && python3 scripts/build.py`
   - **Build output directory:** `dist`
4. **Save and Deploy.** A minute or two later your gallery is live at `https://<project>.pages.dev`.

Optional: add a custom domain under the project's **Custom domains** tab.

### 3. Replace the sample photos

The `photos/` folder ships with generated sample images so you can verify everything works. Delete those folders and add your own.

## Adding photos over time

**Via github.com (no software needed):** open your repo → navigate into `photos/` (or any album) → **Add file → Upload files** → drag photos in → Commit. To create a new album, drag a whole folder from your computer into the upload area. Cloudflare redeploys automatically (~1–3 min).

**Via git locally:** drop files into `photos/...`, commit, push.

Renaming or deleting folders/files in the repo reorganizes the gallery the same way.

## Customizing

- **Gallery title:** edit `config.json`.
- **Image sizes/quality:** constants at the top of `scripts/build.py` (`THUMB_WIDTH`, `WEB_MAX_EDGE`, quality settings).
- **Look and feel:** all CSS is at the top of `site/index.html`.

## Previewing locally (optional)

```bash
pip install -r requirements.txt
python3 scripts/build.py
cd dist && python3 -m http.server 8000   # then open http://localhost:8000
```

The build is incremental locally — already-processed photos are skipped.

## Limits worth knowing

- **Cloudflare Pages free plan:** 20,000 files per deployed site (≈ 10,000 photos at 2 files each), 25 MiB max per file (resized output is far below this), 500 builds/month, unlimited bandwidth.
- **GitHub:** individual files over 100 MB are rejected (photos won't hit this); keep the repo under a few GB total. At a typical 4–6 MB per photo that's a few thousand photos of headroom.
- **Build time:** Cloudflare rebuilds all images on each push (no cache between builds) with a 20-minute timeout — comfortable up to a few thousand photos.
- If you ever approach these, the standard next step is moving images to Cloudflare R2 (object storage) while keeping this same site — ask Claude when you get there.

## Supported formats

JPEG, PNG, WebP, TIFF, BMP. Everything is published as JPEG. Files and folders starting with `.` are ignored.
