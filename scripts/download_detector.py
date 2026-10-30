"""Download a ready-made open mass detector into weights/detector.pt.

Source: https://github.com/Pragata8910/breast_mass_detection (MIT license, YOLOv8 trained on CBIS-DDSM
scanned-film mammograms). NOT RECOMMENDED: its accuracy is not published and in testing it missed an
obvious fibroadenoma. Train your own instead (README: "O'z detektoringizni o'qitish"). Because it has
no validation data, the app keeps warning that "nothing found" does not mean "no lesion".

Security note: a .pt file is a Python pickle and can run code when loaded. Only use checkpoints
from sources you trust.

    python scripts/download_detector.py
"""
from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

URL = "https://raw.githubusercontent.com/Pragata8910/breast_mass_detection/master/best.pt"
DEST = Path(__file__).resolve().parent.parent / "weights" / "detector.pt"


def main() -> int:
    if DEST.exists() and "--force" not in sys.argv:
        print(f"already exists: {DEST} (use --force to download again)")
        return 0
    DEST.parent.mkdir(parents=True, exist_ok=True)
    tmp = DEST.with_suffix(".part")
    print(f"downloading {URL}")

    def progress(blocks, block_size, total):
        if total > 0:
            print(f"\r{min(blocks * block_size / total, 1):.0%}", end="", flush=True)

    urllib.request.urlretrieve(URL, tmp, progress)
    print()
    if tmp.stat().st_size < 1_000_000:  # an HTML error page instead of the weights
        tmp.unlink()
        print("download failed: file is too small")
        return 1
    tmp.rename(DEST)
    print(f"saved -> {DEST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
