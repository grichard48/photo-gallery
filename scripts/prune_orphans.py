#!/usr/bin/env python3
"""Delete R2 objects that the current gallery manifest no longer references.

After you remove photos from photos/ and re-publish, their resized copies stay
in R2 as orphans. This script lists every object in the bucket, compares it
against the photos in dist/manifest.json, and deletes only the ones nothing
points at anymore.

Run it AFTER publishing, so the manifest already reflects the deletions.

Usage:
  python3 scripts/prune_orphans.py            # report, confirm, then delete
  python3 scripts/prune_orphans.py --dry-run  # report only, delete nothing

Loads R2 credentials from .env (same as build.py).
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "dist" / "manifest.json"


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


def referenced_keys(manifest_path):
    """Every R2 key the manifest points at (manifest stores '/i/..', keys are 'i/..')."""
    m = json.loads(manifest_path.read_text(encoding="utf-8"))
    keys = set()

    def walk(node):
        for p in node.get("photos", []):
            for field in ("i", "t"):
                v = p.get(field)
                if v:
                    keys.add(v.lstrip("/"))
        for a in node.get("albums", []):
            walk(a)

    walk(m["root"])
    return keys


def main():
    dry = "--dry-run" in sys.argv[1:]
    if not MANIFEST.exists():
        sys.exit("No dist/manifest.json found. Run ./scripts/publish.sh first.")

    refs = referenced_keys(MANIFEST)
    if not refs:
        sys.exit("The manifest references no images — aborting so we don't wipe "
                 "the bucket. Re-publish and try again.")

    load_dotenv()
    c, bucket = client_bucket()

    have = []
    for pre in ("i/", "t/"):
        have.extend(list_keys(c, bucket, pre))
    orphans = [k for k in have if k not in refs]

    print(f"In R2: {len(have)} objects  |  referenced by manifest: {len(refs)}  "
          f"|  orphans: {len(orphans)}")
    if not orphans:
        print("Nothing to prune — R2 is in sync with the gallery.")
        return

    for k in orphans[:10]:
        print("  orphan:", k)
    if len(orphans) > 10:
        print(f"  ... and {len(orphans) - 10} more")

    frac = len(orphans) / max(len(have), 1)
    if frac > 0.5:
        print(f"\nWARNING: that is {frac * 100:.0f}% of all objects. Make sure you "
              "published the LATEST manifest before pruning.")

    if dry:
        print("\nDry run — nothing deleted.")
        return

    if input(f"\nDelete {len(orphans)} orphaned objects from '{bucket}'? "
             "Type 'yes': ").strip() != "yes":
        print("Aborted.")
        return

    for i in range(0, len(orphans), 1000):
        batch = [{"Key": k} for k in orphans[i:i + 1000]]
        c.delete_objects(Bucket=bucket, Delete={"Objects": batch})
        print(f"  deleted {min(i + 1000, len(orphans))}/{len(orphans)}")
    print("Done.")


if __name__ == "__main__":
    main()
