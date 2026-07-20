#!/usr/bin/env python3
"""Print a Markdown inventory of the current legacy Cypher risk facts."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from evaluation.cypher_inventory import render_inventory_markdown


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cypher", default="data_layer/medical_graph.cypher.txt")
    args = parser.parse_args()
    sys.stdout.write(render_inventory_markdown(args.cypher))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
