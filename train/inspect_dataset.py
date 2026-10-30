"""Print the layout of a downloaded dataset (folders, CSV headers, a few rows).

    python train/inspect_dataset.py --root ~/Downloads/cbis-ddsm

If a prepare_*.py script cannot find the images, send this output to get it adjusted.
"""
from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--depth", type=int, default=3)
    ap.add_argument("--per-dir", type=int, default=4, help="entries shown per folder")
    args = ap.parse_args()
    root = Path(args.root).expanduser()

    print(f"== tree of {root} (depth {args.depth}) ==")
    for dirpath, dirs, files in os.walk(root):
        rel = Path(dirpath).relative_to(root)
        depth = len(rel.parts)
        if depth >= args.depth:
            dirs[:] = []
        dirs.sort()
        indent = "  " * depth
        print(f"{indent}{rel.name or '.'}/  ({len(dirs)} folders, {len(files)} files)")
        for f in sorted(files)[: args.per_dir]:
            print(f"{indent}  {f}")
        del dirs[args.per_dir :]

    print("\n== CSV files ==")
    for dirpath, _, files in os.walk(root):
        for f in sorted(files):
            if f.lower().endswith(".csv"):
                path = Path(dirpath) / f
                with open(path, encoding="utf-8", errors="replace") as fh:
                    rows = list(zip(range(3), csv.reader(fh)))
                print(f"\n-- {path.relative_to(root)}")
                for _, row in rows:
                    print("   ", row)


if __name__ == "__main__":
    main()
