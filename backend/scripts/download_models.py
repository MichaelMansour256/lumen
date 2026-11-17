"""Download model weights from their official release pages.

  python scripts/download_models.py            recommended set (about 425 MB)
  python scripts/download_models.py --all      everything, incl. SwinIR and CodeFormer
  python scripts/download_models.py --only gfpgan yunet
  python scripts/download_models.py --list     show status
  python scripts/download_models.py --verify   re-check recorded SHA-256 checksums
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ai import downloader  # noqa: E402
from app.ai.registry import BY_ID, SPECS  # noqa: E402
from app.config import load_settings  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--only", nargs="+", metavar="ID", choices=sorted(BY_ID))
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    models_dir = load_settings().models_dir

    if args.list or args.verify:
        for spec in SPECS:
            present = spec.path(models_dir).is_file()
            state = "installed" if present else "missing"
            if args.verify and present:
                check = downloader.verify(spec, models_dir)
                state += {True: ", checksum OK", False: ", CHECKSUM MISMATCH", None: ", no checksum"}[check]
            print(f"{spec.id:22} {spec.size_mb:>7} MB  {state:28} {spec.license}")
        return 0

    wanted = [BY_ID[i] for i in args.only] if args.only else [
        s for s in SPECS if args.all or s.recommended]
    failed = 0
    for spec in wanted:
        if spec.path(models_dir).is_file():
            print(f"[ok]   {spec.filename} already present")
            continue
        print(f"[get]  {spec.name} ({spec.size_mb} MB, {spec.license})\n       {spec.url}")

        def progress(done: int, total: int) -> None:
            if total:
                print(f"\r       {done / 2 ** 20:7.1f} / {total / 2 ** 20:.1f} MB", end="", flush=True)

        try:
            downloader.download(spec, models_dir, progress)
            print("\n[done] " + spec.filename)
        except Exception as exc:
            failed += 1
            print(f"\n[FAIL] {spec.filename}: {exc}")
    print(f"\nModels folder: {models_dir}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
