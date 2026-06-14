#!/usr/bin/env python3
"""Rename a top-level album in R2 WITHOUT re-uploading from your Mac.

Renaming a folder changes every image's R2 key, which normally makes build.py
re-upload everything. This script instead moves the images inside R2
(server-side copy — fast and free, no data leaves Cloudflare), deletes the old
copies, and updates .build-cache.json so the next build won't re-upload.

Workflow:
  1. Rename the local folder, e.g. photos/Photos  ->  photos/Scrapbook
  2. python3 scripts/rename_album.py Photos Scrapbook
  3. ./scripts/publish.sh        # rebuilds the manifest, uploads nothing
  4. Commit & push in GitHub Desktop

Loads R2 credentials from .env (same as build.py).
"""
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKERS = 16


def load_dotenv():
    p = ROOT / ".env"
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def client_bucket():
    import boto3
    from botocore.config import Config
    acct = os.environ["R2_ACCOUNT_ID"]
    c = boto3.client(
        "s3",
        endpoint_url=os.environ.get(
            "R2_ENDPOINT", f"https://{acct}.r2.cloudflarestorage.com"),
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        config=Config(region_name="auto",
                      retries={"max_attempts": 5, "mode": "standard"},
                      max_pool_connections=WORKERS + 4),
    )
    return c, os.environ.get("R2_BUCKET", "photo-gallery")


def list_keys(c, bucket, prefix):
    paginator = c.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            yield obj["Key"]


def main():
    if len(sys.argv) != 3:
        sys.exit("Usage: rename_album.py OLD NEW\n"
                 "Example: rename_album.py Photos Scrapbook")
    old, new = sys.argv[1], sys.argv[2]
    load_dotenv()
    c, bucket = client_bucket()

    src_keys = []
    for pre in (f"i/{old}/", f"t/{old}/"):
        src_keys.extend(list_keys(c, bucket, pre))
    if not src_keys:
        sys.exit(f"No objects found under i/{old}/ or t/{old}/. Nothing to do.")

    def new_key(k):
        top, rest = k.split("/", 1)          # e.g. "i", "Photos/Farm/..."
        return f"{top}/{new}/" + rest[len(old) + 1:]

    print(f"Found {len(src_keys)} objects under '{old}'. "
          f"Copying to '{new}' inside R2 (server-side)...")

    def copy_one(k):
        c.copy_object(Bucket=bucket, Key=new_key(k),
                      CopySource={"Bucket": bucket, "Key": k})

    done = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futs = {pool.submit(copy_one, k): k for k in src_keys}
        for f in as_completed(futs):
            f.result()
            done += 1
            if done % 500 == 0 or done == len(src_keys):
                print(f"  copied {done}/{len(src_keys)}")

    print("Deleting old objects...")
    for i in range(0, len(src_keys), 1000):
        batch = [{"Key": k} for k in src_keys[i:i + 1000]]
        c.delete_objects(Bucket=bucket, Delete={"Objects": batch})

    cache_path = ROOT / ".build-cache.json"
    if cache_path.exists():
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
        migrated = {}
        for k, v in cache.items():
            if k.startswith(old + "/"):
                migrated[new + "/" + k[len(old) + 1:]] = v
            else:
                migrated[k] = v
        cache_path.write_text(json.dumps(migrated), encoding="utf-8")
        print("Updated .build-cache.json keys.")

    print(f"\nDone. '{old}' -> '{new}' in R2. "
          "Next: run ./scripts/publish.sh (no upload), then commit & push.")


if __name__ == "__main__":
    main()
