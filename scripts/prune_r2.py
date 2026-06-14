#!/usr/bin/env python3
"""Delete all R2 objects under one or more key prefixes.

Use to clean up orphaned image objects (e.g. after a rename left a stray set).

Usage:
  python3 scripts/prune_r2.py i/Scrapbook/ t/Scrapbook/

Loads R2 credentials from .env (same as build.py) and asks for confirmation
before deleting anything.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


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
                      retries={"max_attempts": 5, "mode": "standard"}),
    )
    return c, os.environ.get("R2_BUCKET", "photo-gallery")


def list_keys(c, bucket, prefix):
    paginator = c.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            yield obj["Key"]


def main():
    prefixes = sys.argv[1:]
    if not prefixes:
        sys.exit("Usage: prune_r2.py <prefix> [prefix ...]\n"
                 "Example: prune_r2.py i/Scrapbook/ t/Scrapbook/")
    load_dotenv()
    c, bucket = client_bucket()

    keys = []
    for pre in prefixes:
        n = 0
        for k in list_keys(c, bucket, pre):
            keys.append(k)
            n += 1
        print(f"{pre}: {n} objects")

    if not keys:
        print("Nothing to delete.")
        return

    print(f"\nAbout to DELETE {len(keys)} objects from bucket '{bucket}'. "
          "This cannot be undone.")
    if input("Type 'yes' to confirm: ").strip() != "yes":
        print("Aborted.")
        return

    for i in range(0, len(keys), 1000):
        batch = [{"Key": k} for k in keys[i:i + 1000]]
        c.delete_objects(Bucket=bucket, Delete={"Objects": batch})
        print(f"  deleted {min(i + 1000, len(keys))}/{len(keys)}")
    print("Done.")


if __name__ == "__main__":
    main()
