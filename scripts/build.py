#!/usr/bin/env python3
"""
Photo gallery build script (R2 edition).

Walks photos/, generates web-size + thumbnail copies of each image, uploads
them to a Cloudflare R2 bucket, and writes dist/manifest.json describing the
album tree. Originals are never uploaded, and EXIF metadata (including GPS) is
stripped from the published copies.

Image requests are served by the Worker (scripts/worker.js) from R2 at the
paths /i/<...> (web) and /t/<...> (thumbnail). Only the small static shell
(index.html, manifest.json, banner.jpg) is deployed as Worker assets.

Incremental: a local .build-cache.json records each source file's size/mtime
and dimensions, so re-runs only resize+upload photos that are new or changed.

Run:  python3 scripts/build.py
Then: npx wrangler deploy        (or just use scripts/publish.sh)

Required credentials (environment variables, or a .env file next to this repo):
  R2_ACCOUNT_ID         Cloudflare account ID
  R2_ACCESS_KEY_ID      R2 API token access key id
  R2_SECRET_ACCESS_KEY  R2 API token secret
  R2_BUCKET             bucket name (default: photo-gallery)
"""

import json
import os
import re
import shutil
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "photos"
SITE = ROOT / "site"
OUT = ROOT / "dist"
CACHE_PATH = ROOT / ".build-cache.json"

THUMB_WIDTH = 600          # px, thumbnail width (2x for retina ~300px)
WEB_MAX_EDGE = 1800        # px, longest edge of web-size image
THUMB_QUALITY = 80
WEB_QUALITY = 85
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp"}
UPLOAD_WORKERS = 12        # concurrent resize+upload tasks
CACHE_CONTROL = "public, max-age=31536000, immutable"

Image.MAX_IMAGE_PIXELS = 300_000_000  # allow big panoramas

MONTHS = {m: i + 1 for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june",
     "july", "august", "september", "october", "november", "december"])}


# ----------------------------------------------------------------------------
# Credentials / R2 client
# ----------------------------------------------------------------------------
def load_dotenv():
    """Minimal .env loader (KEY=VALUE lines); does not overwrite real env vars."""
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key, val = key.strip(), val.strip().strip('"').strip("'")
        os.environ.setdefault(key, val)


def make_r2_client():
    try:
        import boto3
        from botocore.config import Config
    except ImportError:
        sys.exit("boto3 is required. Install with: pip install -r requirements.txt")

    account = os.environ.get("R2_ACCOUNT_ID")
    key_id = os.environ.get("R2_ACCESS_KEY_ID")
    secret = os.environ.get("R2_SECRET_ACCESS_KEY")
    missing = [n for n, v in [
        ("R2_ACCOUNT_ID", account),
        ("R2_ACCESS_KEY_ID", key_id),
        ("R2_SECRET_ACCESS_KEY", secret),
    ] if not v]
    if missing:
        sys.exit("Missing R2 credentials: " + ", ".join(missing) +
                 "\nSet them in environment variables or a .env file "
                 "(see .env.example).")

    endpoint = os.environ.get(
        "R2_ENDPOINT", f"https://{account}.r2.cloudflarestorage.com")
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=key_id,
        aws_secret_access_key=secret,
        config=Config(
            region_name="auto",
            retries={"max_attempts": 5, "mode": "standard"},
            max_pool_connections=UPLOAD_WORKERS + 4,
        ),
    )


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
def natural_key(s: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def album_key(name: str):
    if name.lower() in MONTHS:
        return ["", MONTHS[name.lower()], ""]
    return natural_key(name)


def display_name(raw: str) -> str:
    return raw.replace("_", " ").strip()


def exif_date(path: Path) -> str:
    try:
        exif = Image.open(path).getexif()
        return str(exif.get_ifd(0x8769).get(36867) or exif.get(306) or "")
    except Exception:
        return ""


def load_image(path: Path) -> Image.Image:
    img = Image.open(path)
    img = ImageOps.exif_transpose(img)  # respect camera orientation
    if img.mode in ("RGBA", "P", "LA"):
        img = img.convert("RGBA")
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[-1])
        return bg
    return img.convert("RGB")


def encode_jpeg(img: Image.Image, quality: int) -> bytes:
    buf = BytesIO()
    # No EXIF passed -> metadata (incl. GPS) is stripped from published copies
    img.save(buf, "JPEG", quality=quality, optimize=True, progressive=True)
    return buf.getvalue()


# ----------------------------------------------------------------------------
# Per-photo processing (resize + upload, or skip via cache)
# ----------------------------------------------------------------------------
def process_photo(client, bucket, src: Path, rel: Path, cache, cache_lock):
    """Return manifest-ready meta for one photo. Uploads to R2 unless cached."""
    rel_key = rel.with_suffix(".jpg").as_posix()
    web_key = "i/" + rel_key
    thumb_key = "t/" + rel_key

    st = src.stat()
    sig = [int(st.st_mtime), st.st_size]

    with cache_lock:
        cached = cache.get(rel.as_posix())
    if cached and cached.get("sig") == sig and "w" in cached:
        # Unchanged since last upload -> reuse stored dimensions/date.
        return _entry(rel, cached["w"], cached["h"], cached.get("d", ""),
                      web_key, thumb_key), False

    date = exif_date(src)
    img = load_image(src)
    w, h = img.size

    # web-size
    scale = min(1.0, WEB_MAX_EDGE / max(w, h))
    web = img.resize((round(w * scale), round(h * scale)), Image.LANCZOS) if scale < 1 else img
    client.put_object(Bucket=bucket, Key=web_key, Body=encode_jpeg(web, WEB_QUALITY),
                      ContentType="image/jpeg", CacheControl=CACHE_CONTROL)
    # thumbnail
    tscale = min(1.0, THUMB_WIDTH / w)
    thumb = img.resize((round(w * tscale), round(h * tscale)), Image.LANCZOS) if tscale < 1 else img
    client.put_object(Bucket=bucket, Key=thumb_key, Body=encode_jpeg(thumb, THUMB_QUALITY),
                      ContentType="image/jpeg", CacheControl=CACHE_CONTROL)

    with cache_lock:
        cache[rel.as_posix()] = {"sig": sig, "w": w, "h": h, "d": date}
    return _entry(rel, w, h, date, web_key, thumb_key), True


def _entry(rel: Path, w, h, d, web_key, thumb_key):
    return {
        "name": display_name(rel.stem),
        "t": "/" + thumb_key,
        "i": "/" + web_key,
        "w": w,
        "h": h,
        "d": d,
    }


# ----------------------------------------------------------------------------
# Tree assembly (built from the metadata gathered above)
# ----------------------------------------------------------------------------
def list_photos(dir_path: Path):
    """Yield (src, rel) for every image under photos/, skipping dotfiles."""
    for entry in sorted(dir_path.iterdir(), key=lambda p: natural_key(p.name)):
        if entry.name.startswith("."):
            continue
        if entry.is_dir():
            yield from list_photos(entry)
        elif entry.suffix.lower() in IMAGE_EXTS:
            yield entry, entry.relative_to(SRC)


def _find_thumb(photos, albums, stem):
    """Depth-first search for a photo whose filename stem matches `stem`."""
    for p in photos:
        if Path(p["i"].rsplit("/", 1)[-1]).stem.lower() == stem:
            return p["t"]
    for a in albums:
        hit = _find_thumb(a["photos"], a["albums"], stem)
        if hit:
            return hit
    return None


def build_album(dir_path: Path, meta: dict) -> dict:
    rel = dir_path.relative_to(SRC)
    entries = sorted(dir_path.iterdir(), key=lambda p: natural_key(p.name))

    photos, albums = [], []
    for entry in entries:
        if entry.name.startswith("."):
            continue
        if entry.is_dir():
            sub = build_album(entry, meta)
            if sub["count"] > 0:
                albums.append(sub)
        elif entry.suffix.lower() in IMAGE_EXTS:
            m = meta.get(entry.relative_to(SRC).as_posix())
            if m:
                photos.append(m)

    photos.sort(key=lambda p: (p["d"] or "9999", natural_key(p["name"])))
    albums.sort(key=lambda a: album_key(a["name"]))

    count = len(photos) + sum(a["count"] for a in albums)
    cover = photos[0]["t"] if photos else (albums[0]["cover"] if albums else None)

    # Optional: a ".cover" file naming an image overrides the auto-chosen cover.
    # The image can live directly in this folder or anywhere beneath it.
    marker = dir_path / ".cover"
    if marker.exists():
        try:
            target = marker.read_text(encoding="utf-8").strip()
        except Exception:
            target = ""
        if target:
            chosen = _find_thumb(photos, albums, Path(target).stem.lower())
            if chosen:
                cover = chosen
            else:
                print(f"  ! .cover in '{rel}': no photo named '{target}' found",
                      file=sys.stderr)

    return {
        "name": display_name(rel.name) if rel.name else "Home",
        "path": rel.as_posix() if rel.name else "",
        "cover": cover,
        "count": count,
        "albums": albums,
        "photos": photos,
    }


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------
def have_r2_creds():
    return all(os.environ.get(k) for k in
               ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY"))


def copy_shell():
    """Copy the static shell (index.html, banner.jpg, ...) into dist/."""
    OUT.mkdir(exist_ok=True)
    for asset in SITE.iterdir():
        if asset.is_file() and not asset.name.startswith("."):
            shutil.copy(asset, OUT / asset.name)


def main():
    load_dotenv()

    # Deploy-only mode: no R2 credentials present (e.g. running inside
    # Cloudflare's build, where .env is absent). Skip resizing/uploading and
    # rely on the committed dist/manifest.json so `wrangler deploy` can ship it.
    if not have_r2_creds():
        if (OUT / "manifest.json").exists():
            copy_shell()
            print("No R2 credentials found -> deploy-only mode "
                  "(using committed dist/manifest.json). Skipping upload.")
            return
        sys.exit("Missing R2 credentials and no prebuilt dist/manifest.json.\n"
                 "Set credentials in .env (see .env.example) to build + upload.")

    if not SRC.is_dir():
        sys.exit("No photos/ folder found. Create it and add some images.")

    client = make_r2_client()
    bucket = os.environ.get("R2_BUCKET", "photo-gallery")

    config = {"title": "My Photos"}
    config_path = ROOT / "config.json"
    if config_path.exists():
        config.update(json.loads(config_path.read_text(encoding="utf-8")))

    cache = {}
    if CACHE_PATH.exists():
        try:
            cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            cache = {}
    cache_lock = threading.Lock()

    photos = list(list_photos(SRC))
    total = len(photos)
    if total == 0:
        sys.exit("No images found under photos/.")
    print(f"Found {total} photos. Processing (uploading new/changed to R2 '{bucket}')...")

    meta = {}
    uploaded = 0
    done = 0
    errors = 0
    with ThreadPoolExecutor(max_workers=UPLOAD_WORKERS) as pool:
        futs = {
            pool.submit(process_photo, client, bucket, src, rel, cache, cache_lock): rel
            for src, rel in photos
        }
        for fut in as_completed(futs):
            rel = futs[fut]
            done += 1
            try:
                entry, did_upload = fut.result()
                meta[rel.as_posix()] = entry
                if did_upload:
                    uploaded += 1
            except Exception as e:
                errors += 1
                print(f"  ! {rel}: {e}", file=sys.stderr)
            if done % 200 == 0 or done == total:
                print(f"  {done}/{total}  ({uploaded} uploaded this run)")
            if done % 500 == 0:  # periodic cache checkpoint
                with cache_lock:
                    CACHE_PATH.write_text(json.dumps(cache), encoding="utf-8")

    with cache_lock:
        CACHE_PATH.write_text(json.dumps(cache), encoding="utf-8")

    tree = build_album(SRC, meta)

    OUT.mkdir(exist_ok=True)
    manifest = {"title": config["title"], "root": tree}
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    # copy static shell (index.html, banner.jpg, ...) into dist for deploy
    for asset in SITE.iterdir():
        if asset.is_file() and not asset.name.startswith("."):
            shutil.copy(asset, OUT / asset.name)

    print(f"Done: {tree['count']} photos in manifest, {uploaded} uploaded this run, "
          f"{errors} errors. Deploy with: npx wrangler deploy")


if __name__ == "__main__":
    main()
