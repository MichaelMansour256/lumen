"""Create backend/.env.public for start_public.bat (run once).

  python scripts/make_public_env.py https://your-site.vercel.app
"""
from __future__ import annotations

import secrets
import sys
from pathlib import Path

TARGET = Path(__file__).resolve().parent.parent / ".env.public"

TEMPLATE = """# Settings used by start_public.bat (internet-facing mode). Edit freely, then restart.
ENHANCER_PUBLIC=1
# Anyone with this key can use your GPU. Change it to revoke old share links.
ENHANCER_ACCESS_KEY={key}
# Your Vercel site; used for CORS and to build the share link.
LUMEN_SITE_URL={site}
ENHANCER_ALLOWED_ORIGINS={site},http://localhost:3000,http://127.0.0.1:3000
# Vercel preview deployments, e.g.  ^https://lumen-[a-z0-9-]+\\.vercel\\.app$
ENHANCER_ALLOWED_ORIGIN_REGEX=
ENHANCER_ALLOWED_HOSTS=127.0.0.1,localhost,*.trycloudflare.com

# Separate storage from local use; files are deleted after 2 hours.
ENHANCER_DATA_DIR=data_public
ENHANCER_FILE_TTL_HOURS=2

# Smaller limits than local mode, to keep the PC responsive.
ENHANCER_MAX_UPLOAD_MB=15
ENHANCER_MAX_FILES_PER_UPLOAD=5
ENHANCER_MAX_INPUT_PIXELS=16000000
ENHANCER_MAX_OUTPUT_PIXELS=64000000
ENHANCER_MAX_OUTPUT_SIDE=12000
ENHANCER_JOB_TIMEOUT_S=900

# Per visitor, per hour (0 = unlimited) and queue caps.
ENHANCER_RATE_UPLOADS_PER_HOUR=30
ENHANCER_RATE_JOBS_PER_HOUR=20
ENHANCER_MAX_QUEUED_PER_CLIENT=3
ENHANCER_MAX_QUEUED_JOBS=10
"""


def main() -> int:
    if TARGET.exists():
        print(f"{TARGET.name} already exists - leaving it unchanged.")
        return 0
    site = (sys.argv[1] if len(sys.argv) > 1 else "").strip().rstrip("/")
    if site and not site.startswith(("https://", "http://")):
        site = "https://" + site
    if not site.startswith("https://") or " " in site or "," in site:
        print("Give the full https:// address of your Vercel site, e.g. https://lumen.vercel.app")
        return 1
    TARGET.write_text(TEMPLATE.format(key=secrets.token_urlsafe(24), site=site), encoding="utf-8")
    print(f"Created {TARGET.name} with a new access key.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
