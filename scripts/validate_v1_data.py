#!/usr/bin/env python3
"""Validate the source-aligned V1 catalog and print a concise summary."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from medsafety.catalog import KnowledgeCatalog


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default="data/v1")
    args = parser.parse_args()
    catalog = KnowledgeCatalog.from_directory(args.data_dir)
    print(f"data_version={catalog.data_version}")
    print(f"sources={len(catalog.sources)}")
    print(f"medications={len(catalog.medications)}")
    print(f"facts={len(catalog.facts)}")
    print("status=valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
