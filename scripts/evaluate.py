#!/usr/bin/env python3
"""Run a reproducible offline baseline and print JSON or Markdown to stdout."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from evaluation.dataset import load_cases
from evaluation.entity_baseline import evaluate_entity_extractor, render_markdown
from evaluation.safety_engine_baseline import evaluate_safety_engine, render_safety_markdown
from logic_layer.entity_utils import exact_entity_extraction
from medsafety.catalog import KnowledgeCatalog
from medsafety.safety_engine import SafetyEngine


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default="eval/dev_cases.jsonl")
    parser.add_argument("--runner", choices=("rule_entities", "safety_engine"), default="rule_entities")
    parser.add_argument("--data-dir", default="data/v1")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    cases = load_cases(dataset_path)
    if args.runner == "rule_entities":
        report = evaluate_entity_extractor(cases, exact_entity_extraction)
        markdown = render_markdown(report, str(dataset_path))
    else:
        catalog = KnowledgeCatalog.from_directory(args.data_dir)
        report = evaluate_safety_engine(cases, SafetyEngine(catalog))
        report["data_version"] = catalog.data_version
        markdown = render_safety_markdown(report, str(dataset_path), catalog.data_version)

    if args.format == "markdown":
        sys.stdout.write(markdown)
    else:
        json.dump(report, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
