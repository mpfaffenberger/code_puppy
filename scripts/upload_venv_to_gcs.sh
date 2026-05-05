#!/usr/bin/env bash
# ============================================================================
# upload_venv_to_gcs.sh - Upload portable code-puppy venv zip to GCS (Mac)
# ============================================================================
# Bash equivalent of upload_venv_to_gcs.ps1. Auth + upload logic lives in an
# inline Python heredoc so we can lean on google-auth + requests instead of
# hand-rolling JWT signing in shell.
#
# Uploads to:
#   gs://<bucket>/code-puppy-venv/<version>/code-puppy-venv-<platform>.zip
# When --write-latest is passed, also writes:
#   gs://<bucket>/code-puppy-venv/latest/version.txt   (no trailing newline)
# ============================================================================
set -euo pipefail

ZIP_PATH=""
VERSION=""
SA_KEY_B64=""
BUCKET="puppy-pages"
PLATFORM="mac"
WRITE_LATEST="false"

usage() {
    cat <<EOF
Usage: $0 --zip-path PATH --version VER --sa-key-b64 B64 [options]

Required:
  --zip-path PATH      Path to the venv zip
  --version VER        code-puppy version string
  --sa-key-b64 B64     Base64-encoded GCS service account JSON

Optional:
  --bucket NAME        GCS bucket (default: puppy-pages)
  --platform NAME      Platform tag (default: mac)
  --write-latest       Also write code-puppy-venv/latest/version.txt
  -h, --help           Show this help
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --zip-path)     ZIP_PATH="$2"; shift 2 ;;
        --version)      VERSION="$2"; shift 2 ;;
        --sa-key-b64)   SA_KEY_B64="$2"; shift 2 ;;
        --bucket)       BUCKET="$2"; shift 2 ;;
        --platform)     PLATFORM="$2"; shift 2 ;;
        --write-latest) WRITE_LATEST="true"; shift ;;
        -h|--help)      usage; exit 0 ;;
        *)              echo "Unknown arg: $1" >&2; usage; exit 1 ;;
    esac
done

[ -n "$ZIP_PATH" ]   || { echo "ERROR: --zip-path required" >&2; exit 1; }
[ -n "$VERSION" ]    || { echo "ERROR: --version required" >&2; exit 1; }
[ -n "$SA_KEY_B64" ] || { echo "ERROR: --sa-key-b64 required" >&2; exit 1; }
[ -f "$ZIP_PATH" ]   || { echo "ERROR: Zip not found: $ZIP_PATH" >&2; exit 1; }

ZIP_SIZE_MB=$(python3 -c "import os; print(round(os.path.getsize('$ZIP_PATH')/1048576, 2))")
echo "Zip      : $ZIP_PATH (${ZIP_SIZE_MB} MB)"
echo "Version  : $VERSION"
echo "Bucket   : $BUCKET"
echo "Platform : $PLATFORM"
echo "Latest   : $WRITE_LATEST"

# Honor HTTPS_PROXY if already set, else default to Walmart sysproxy.
PROXY_URL="${HTTPS_PROXY:-http://sysproxy.wal-mart.com:8080}"
echo "Proxy    : $PROXY_URL"

export GCS_SA_KEY_B64_INNER="$SA_KEY_B64"
export GCS_ZIP_PATH="$ZIP_PATH"
export GCS_VERSION="$VERSION"
export GCS_BUCKET="$BUCKET"
export GCS_PLATFORM="$PLATFORM"
export GCS_WRITE_LATEST="$WRITE_LATEST"
export GCS_PROXY_URL="$PROXY_URL"

python3 - <<'PYEOF'
import base64
import json
import os
import sys

import requests
from google.auth.transport.requests import Request
from google.oauth2 import service_account

sa_b64    = os.environ["GCS_SA_KEY_B64_INNER"]
zip_path  = os.environ["GCS_ZIP_PATH"]
version   = os.environ["GCS_VERSION"]
bucket    = os.environ["GCS_BUCKET"]
platform  = os.environ["GCS_PLATFORM"]
write_lat = os.environ["GCS_WRITE_LATEST"] == "true"
proxy     = os.environ["GCS_PROXY_URL"]
proxies   = {"https": proxy, "http": proxy}

print("Decoding service account key...")
sa_info = json.loads(base64.b64decode(sa_b64))
print(f"Service account: {sa_info.get('client_email', '<unknown>')}")

creds = service_account.Credentials.from_service_account_info(
    sa_info,
    scopes=["https://www.googleapis.com/auth/devstorage.read_write"],
)
print("Obtaining GCS access token...")
creds.refresh(Request())
print("Access token obtained.")

def upload(local_path, object_name, content_type):
    url = (
        f"https://storage.googleapis.com/upload/storage/v1/b/{bucket}/o"
        f"?uploadType=media&name={requests.utils.quote(object_name, safe='')}"
    )
    print(f"Uploading to gs://{bucket}/{object_name} ...")
    with open(local_path, "rb") as fh:
        data = fh.read()
    resp = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {creds.token}",
            "Content-Type": content_type,
        },
        data=data,
        proxies=proxies,
        timeout=600,
    )
    resp.raise_for_status()
    body = resp.json()
    print(f"  OK - size: {body.get('size')} bytes")

zip_object = f"code-puppy-venv/{version}/code-puppy-venv-{platform}.zip"
upload(zip_path, zip_object, "application/zip")

if write_lat:
    import tempfile
    with tempfile.NamedTemporaryFile("wb", delete=False, suffix=".txt") as tmp:
        tmp.write(version.encode("ascii"))   # no trailing newline
        tmp_path = tmp.name
    try:
        upload(tmp_path, "code-puppy-venv/latest/version.txt", "text/plain")
    finally:
        os.unlink(tmp_path)

print()
print("=== Upload complete ===")
print(f"  Version  : {version}")
print(f"  Bucket   : {bucket}")
print(f"  Platform : {platform}")
if write_lat:
    print("  Latest pointer updated.")
PYEOF
