#!/usr/bin/env python3
"""Run a reproducible offline baseline and print JSON or Markdown to stdout."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
from pathlib import Path
import subprocess
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from evaluation.dataset import load_cases, load_explanation_guardrail_cases
from evaluation.entity_baseline import evaluate_entity_extractor, render_markdown
from evaluation.explanation_guardrails import (
    evaluate_explanation_guardrails,
    render_explanation_guardrails_markdown,
)
from evaluation.safety_engine_baseline import evaluate_safety_engine, render_safety_markdown
from logic_layer.entity_utils import exact_entity_extraction
from medsafety.catalog import KnowledgeCatalog
from medsafety.safety_engine import SafetyEngine


def git_state() -> tuple[str, bool]:
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    dirty = bool(
        subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=REPOSITORY_ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    )
    return commit, dirty


def main() -> int:
    logging.basicConfig(level=logging.ERROR)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default="eval/dev_cases.jsonl")
    parser.add_argument(
        "--runner",
        choices=("rule_entities", "safety_engine", "explanation_guardrails"),
        default="rule_entities",
    )
    parser.add_argument("--data-dir", default="data/v1")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    if args.runner == "rule_entities":
        cases = load_cases(dataset_path)
        report = evaluate_entity_extractor(cases, exact_entity_extraction)
        markdown = render_markdown(report, str(dataset_path))
    elif args.runner == "safety_engine":
        cases = load_cases(dataset_path)
        catalog = KnowledgeCatalog.from_directory(args.data_dir)
        report = evaluate_safety_engine(cases, SafetyEngine(catalog))
        report["data_version"] = catalog.data_version
        markdown = render_safety_markdown(report, str(dataset_path), catalog.data_version)
    else:
        cases = load_explanation_guardrail_cases(dataset_path)
        catalog = KnowledgeCatalog.from_directory(args.data_dir)
        report = evaluate_explanation_guardrails(cases, SafetyEngine(catalog))
        report["data_version"] = catalog.data_version
        report["dataset_sha256"] = hashlib.sha256(dataset_path.read_bytes()).hexdigest()
        report["code_commit"], report["working_tree_dirty"] = git_state()
        markdown = render_explanation_guardrails_markdown(
            report,
            str(dataset_path),
            catalog.data_version,
        )

    if args.format == "markdown":
        sys.stdout.write(markdown)
    else:
        json.dump(report, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
