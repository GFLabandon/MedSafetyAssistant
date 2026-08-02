#!/usr/bin/env python3
"""Evaluate name-only Ollama routing with server-bound arguments on dev cases."""

from __future__ import annotations

import argparse
import hashlib
from importlib.metadata import version as package_version
import json
from pathlib import Path
import subprocess
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from config import Config
from evaluation.server_bound_tool import (
    evaluate_server_bound_tools,
    render_server_bound_tool_markdown,
)
from evaluation.tool_shadow_dataset import load_shadow_tool_cases
from medsafety.catalog import KnowledgeCatalog
from medsafety.entity_resolution import V1EntityResolver
from medsafety.explanation import EvidenceGroundedExplainer
from medsafety.safety_engine import SafetyEngine
from medsafety.server_bound_tool_decisions import OllamaToolNamePlanner
from medsafety.tool_workflow import TypedSafetyWorkflow
from scripts.evaluate_tool_shadow import installed_model_metadata


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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default="eval/tool_shadow_v1.jsonl")
    parser.add_argument("--split", choices=("dev",), default="dev")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    parser.add_argument("--ollama-url", default=Config.OLLAMA_URL)
    parser.add_argument("--model", default=Config.OLLAMA_TOOL_MODEL)
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument("--output")
    parser.add_argument("--records-output")
    args = parser.parse_args()

    cases = load_shadow_tool_cases(args.dataset, split=args.split)
    if not cases:
        raise ValueError("dataset contains no development cases")
    catalog = KnowledgeCatalog.from_directory(REPOSITORY_ROOT / "data/v1")
    workflow = TypedSafetyWorkflow(
        resolver=V1EntityResolver(catalog),
        engine=SafetyEngine(catalog),
        explainer=EvidenceGroundedExplainer(),
    )
    planner = OllamaToolNamePlanner(
        host=args.ollama_url,
        model=args.model,
        timeout_seconds=args.timeout_seconds,
    )
    model_metadata = installed_model_metadata(planner)
    report, records = evaluate_server_bound_tools(
        cases,
        planner,
        workflow.registry.definitions(),
        repetitions=args.repetitions,
    )
    dataset_path = Path(args.dataset)
    report.update(
        {
            "split": args.split,
            "dataset_sha256": hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
            "model": model_metadata,
            "configured_model": args.model,
            "ollama_url": args.ollama_url,
            "ollama_package_version": package_version("ollama"),
        }
    )
    report["code_commit"], report["working_tree_dirty"] = git_state()

    if args.records_output:
        Path(args.records_output).write_text(
            json.dumps(records, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    rendered = (
        render_server_bound_tool_markdown(report, str(dataset_path))
        if args.format == "markdown"
        else json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
