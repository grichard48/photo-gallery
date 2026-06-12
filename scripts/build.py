#!/usr/bin/env python3
"""
Photo gallery build script.

Walks photos/, generates thumbnails + web-size images into dist/,
and writes a manifest.json describing the album tree.

Run:  python3 scripts/build.py
Output: dist/  (deploy this folder)
"""

import json
import re
import shutil
import sys
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "photos"
SITE = ROOT / "site"
OUT = ROOT / "dist"

THUMB_WIDTH = 600          # px, thumbnail width (2x for retina display ~300px)
WEB_MAX_EDGE = 1800        # px, longest edge of web-size image
THUMB_QUALITY = 80
WEB_QUALITY = 85
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp"}

Image.MAX_IMAGE_PIXELS = 300_000_000  # allow big panoramas

MONTHS = {m: i + 1 for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june",
     "july", "august", "september", "october", "november", "december"])}


def natural_key(s: str):
    """Sort so that img2 comes before img10."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def album_key(name: str):
    """Sort albums naturally, except month names sort chronologically."""
    if name.lower() in MONTHS:
        return ["", MONTHS[name.lower()], ""]
    return natural_key(name)


def exif_date(path: Path) -> str:
    """Capture date as 'YYYY:MM:DD HH:MM:SS', or '' if unavailable."""
    try:
        exif = Image.open(path).getexif()
        return str(exif.get_ifd(0x8769).get(36867) or exif.get(306) or "")
    except Exception:
        return ""


def display_name(raw: str) -> str:
    """Folder/file name -> display title: underscores to spaces."""
    return raw.replace("_", " ").strip()


def load_image(path: Path) -> Image.Image:
    img = Image.open(path)
    img = ImageOps.exif_transpose(img)  # respect camera orientation
    if img.mode in ("RGBA", "P", "LA"):
        # flatten transparency onto white
        img = img.convert("RGBA")
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[-1])
        return bg
    return img.convert("RGB")


def save_jpeg(img: Image.Image, dest: Path, quality: int):
    dest.parent.mkdir(parents=True, exist_ok=True)
    # No EXIF passed -> metadata (incl. GPS) is stripped from published copies
    img.save(dest, "JPEG", quality=quality, optimize=True, progressive=True)


def process_photo(src: Path, rel: Path):
    """Generate thumb + web image if missing/stale. Returns photo manifest entry."""
    out_name = rel.with_suffix(".jpg")
    thumb_dest = OUT / "t" / out_name
    web_dest = OUT / "i" / out_name

    img = load_image(src)
    w, h = img.size

    stale = (
        not thumb_dest.exists()
        or not web_dest.exists()
        or thumb_dest.stat().st_mtime < src.stat().st_mtime
    )
    if stale:
        # web-size
        scale = min(1.0, WEB_MAX_EDGE / max(w, h))
        web = img.resize((round(w * scale), round(h * scale)), Image.LANCZOS) if scale < 1 else img
        save_jpeg(web, web_dest, WEB_QUALITY)
        # thumbnail
        tscale = min(1.0, THUMB_WIDTH / w)
        thumb = img.resize((round(w * tscale), round(h * tscale)), Image.LANCZOS) if tscale < 1 else img
        save_jpeg(thumb, thumb_dest, THUMB_QUALITY)

    return {
        "name": display_name(rel.stem),
        "t": str(Path("t") / out_name).replace("\\", "/"),
        "i": str(Path("i") / out_name).replace("\\", "/"),
        "w": w,
        "h": h,
        "d": exif_date(src),
    }


def build_album(dir_path: Path) -> dict:
    rel = dir_path.relative_to(SRC)
    entries = sorted(dir_path.iterdir(), key=lambda p: natural_key(p.name))

    photos, albums = [], []
    for entry in entries:
        if entry.name.startswith("."):
            continue
        if entry.is_dir():
            sub = build_album(entry)
            if sub["count"] > 0:  # skip empty folders
                albums.append(sub)
        elif entry.suffix.lower() in IMAGE_EXTS:
            try:
                photos.append(process_photo(entry, entry.relative_to(SRC)))
            except Exception as e:
                print(f"  ! skipping {entry.relative_to(SRC)}: {e}", file=sys.stderr)

    photos.sort(key=lambda p: (p["d"] or "9999", natural_key(p["name"])))
    albums.sort(key=lambda a: album_key(a["name"]))

    count = len(photos) + sum(a["count"] for a in albums)
    cover = photos[0]["t"] if photos else (albums[0]["cover"] if albums else None)
    return {
        "name": display_name(rel.name) if rel.name else "Home",
        "path": str(rel).replace("\\", "/") if rel.name else "",
        "cover": cover,
        "count": count,
        "albums": albums,
        "photos": photos,
    }


def main():
    if not SRC.is_dir():
        sys.exit("No photos/ folder found. Create it and add some images.")

    config = {"title": "My Photos"}
    config_path = ROOT / "config.json"
    if config_path.exists():
        config.update(json.loads(config_path.read_text(encoding="utf-8")))

    print("Building gallery...")
    tree = build_album(SRC)
    if tree["count"] == 0:
        sys.exit("No images found under photos/.")

    OUT.mkdir(exist_ok=True)
    manifest = {"title": config["title"], "root": tree}
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    # copy all site assets (index.html, banner.jpg, ...) into dist
    for asset in SITE.iterdir():
        if asset.is_file() and not asset.name.startswith("."):
            shutil.copy(asset, OUT / asset.name)
    # modest edge/browser caching for images; manifest stays fresh
    (OUT / "_headers").write_text(
        "/t/*\n  Cache-Control: public, max-age=604800\n"
        "/i/*\n  Cache-Control: public, max-age=604800\n"
        "/manifest.json\n  Cache-Control: no-cache\n",
        encoding="utf-8",
    )
    print(f"Done: {tree['count']} photos -> {OUT}")


if __name__ == "__main__":
    main()
