#!/usr/bin/env bash
# Publish the gallery: resize + upload new/changed photos to R2 and rebuild the
# manifest. Deployment happens when you commit & push (Cloudflare auto-deploys).
#
# Usage:  ./scripts/publish.sh
#
# Requires: python3 with deps installed (pip install -r requirements.txt) and a
# .env file with your R2 credentials.
set -euo pipefail

cd "$(dirname "$0")/.."

echo "==> Building (resize + upload new/changed photos to R2)..."
python3 scripts/build.py

echo
echo "==> Upload complete. To publish the changes:"
echo "    Open GitHub Desktop, commit the changes, and click Push origin."
echo "    Cloudflare redeploys automatically (~2-3 min)."
