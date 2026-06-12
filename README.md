# Photo Gallery

A simple static photo gallery. Folders inside `photos/` become albums (nesting supported). Push to GitHub, and Cloudflare rebuilds and deploys automatically.

## How it works

```
photo-gallery/
├── photos/            ← your photos, organized in folders (this is all you touch)
│   ├── 2025/December/
│   └── 2026/March/
├── config.json        ← gallery title
├── site/index.html    ← the gallery web page
├── site/banner.jpg    ← home page banner image (optional)
├── scripts/build.py   ← generates thumbnails + web-size images into dist/
├── wrangler.jsonc     ← Cloudflare deploy config
└── requirements.txt
```

On every push, Cloudflare runs `build.py`, which creates resized copies of each photo (originals are never published, and EXIF metadata — including GPS location — is stripped from the published copies) plus a `manifest.json` the page uses for navigation. Everything in `site/` is published as-is.

Folder names become album titles; underscores display as spaces (`Spring_Garden` → "Spring Garden"). Photos sort by capture date (from EXIF, falling back to filename); albums sort alphabetically, except folders named after months, which sort chronologically (March before April before May).

## Cloudflare setup (already done)

The project is connected to this GitHub repo as a Cloudflare **Workers** project:

- **Build command:** `pip install -r requirements.txt && python3 scripts/build.py`
- **Deploy command:** `npx wrangler deploy`
- `wrangler.jsonc` contains `"name": "photo-gallery"` — this must match the Cloudflare project name.

Every push to the default branch triggers a rebuild and redeploy (~2–3 min).

## Adding photos over time

Drop files into `photos/<album>/` (create folders freely — they become albums), then commit and push with GitHub Desktop. That's it.

## Customizing

- **Gallery title:** edit `config.json`.
- **Home page banner:** replace `site/banner.jpg` (a wide crop, ~2000px across, works best). Delete it to remove the banner — the page handles its absence gracefully.
- **Colors:** CSS variables in the `:root` block at the top of `site/index.html` (`--bg`, `--fg`, `--accent`, etc.).
- **Image sizes/quality:** constants at the top of `scripts/build.py` (`THUMB_WIDTH`, `WEB_MAX_EDGE`, quality settings).

## Previewing locally (optional)

```bash
pip install -r requirements.txt
python3 scripts/build.py
cd dist && python3 -m http.server 8000   # then open http://localhost:8000
```

The build is incremental locally — already-processed photos are skipped. `dist/` is gitignored; it's generated, never committed.

## Limits worth knowing

- **Cloudflare free plan:** 20,000 files per deployed site (≈ 10,000 photos at 2 files each), 25 MiB max per file, unlimited bandwidth.
- **GitHub:** individual files over 100 MB are rejected; keep the repo under a few GB total. At a typical 4–6 MB per photo that's a few thousand photos of headroom.
- **Build time:** Cloudflare rebuilds all images on each push with a 20-minute timeout — comfortable up to a few thousand photos.
- If you ever approach these, the standard next step is moving images to Cloudflare R2 (object storage) while keeping this same site — ask Claude when you get there.

## Supported formats

JPEG, PNG, WebP, TIFF, BMP. Everything is published as JPEG. Files and folders starting with `.` are ignored.
