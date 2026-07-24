#!/usr/bin/env python3
"""Run a reproducible offline baseline and print JSON or Markdown to stdout."""

from __future__ import annotations

import argparse
import hashlib
from importlib.metadata import version as package_version
import json
import logging
from pathlib import Path
import subprocess
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from evaluation.dataset import (
    load_cases,
    load_explanation_guardrail_cases,
    load_opaque_planner_cases,
)
from evaluation.entity_baseline import evaluate_entity_extractor, render_markdown
from evaluation.explanation_guardrails import (
    evaluate_explanation_guardrails,
    render_explanation_guardrails_markdown,
)
from evaluation.ollama_explanation import (
    evaluate_ollama_explanations,
    render_ollama_explanation_markdown,
)
from evaluation.opaque_id_planner import (
    evaluate_opaque_id_planner,
    render_opaque_id_markdown,
)
from evaluation.safety_engine_baseline import evaluate_safety_engine, render_safety_markdown
from config import Config
from logic_layer.entity_utils import exact_entity_extraction
from medsafety.catalog import KnowledgeCatalog
from medsafety.ollama_planner import OllamaExplanationPlanner
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


def ollama_model_metadata(planner: OllamaExplanationPlanner) -> dict[str, object]:
    response = planner.client.list()
    models = response.get("models", []) if isinstance(response, dict) else response.models
    for model in models:
        payload = (
            model
            if isinstance(model, dict)
            else model.model_dump(mode="json", exclude_none=True)
        )
        name = payload.get("model") or payload.get("name")
        if name != planner.model:
            continue
        details = payload.get("details") or {}
        return {
            "name": name,
            "digest": payload.get("digest"),
            "size_bytes": payload.get("size"),
            "modified_at": payload.get("modified_at"),
            "parameter_size": details.get("parameter_size"),
            "quantization_level": details.get("quantization_level"),
            "family": details.get("family"),
            "format": details.get("format"),
        }
    raise ValueError(f"configured Ollama model is not installed: {planner.model}")


def main() -> int:
    logging.basicConfig(level=logging.ERROR)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default="eval/dev_cases.jsonl")
    parser.add_argument(
        "--runner",
        choices=(
            "rule_entities",
            "safety_engine",
            "explanation_guardrails",
            "ollama_explanation",
            "ollama_opaque_ids",
        ),
        default="rule_entities",
    )
    parser.add_argument("--data-dir", default="data/v1")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    parser.add_argument("--ollama-url", default=Config.OLLAMA_URL)
    parser.add_argument("--model", default=Config.OLLAMA_MODEL)
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
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
    elif args.runner == "explanation_guardrails":
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
    elif args.runner == "ollama_explanation":
        cases = load_cases(dataset_path)
        catalog = KnowledgeCatalog.from_directory(args.data_dir)
        planner = OllamaExplanationPlanner(
            host=args.ollama_url,
            model=args.model,
            timeout_seconds=args.timeout_seconds,
        )
        report = evaluate_ollama_explanations(
            cases,
            SafetyEngine(catalog),
            planner,
            repetitions=args.repetitions,
        )
        report["data_version"] = catalog.data_version
        report["dataset_sha256"] = hashlib.sha256(dataset_path.read_bytes()).hexdigest()
        report["model"] = ollama_model_metadata(planner)
        report["ollama_url"] = args.ollama_url
        report["ollama_package_version"] = package_version("ollama")
        report["code_commit"], report["working_tree_dirty"] = git_state()
        markdown = render_ollama_explanation_markdown(report, str(dataset_path))
    else:
        cases = load_opaque_planner_cases(dataset_path)
        planner = OllamaExplanationPlanner(
            host=args.ollama_url,
            model=args.model,
            timeout_seconds=args.timeout_seconds,
        )
        report = evaluate_opaque_id_planner(
            cases,
            planner,
            repetitions=args.repetitions,
        )
        report["dataset_sha256"] = hashlib.sha256(dataset_path.read_bytes()).hexdigest()
        report["model"] = ollama_model_metadata(planner)
        report["ollama_url"] = args.ollama_url
        report["ollama_package_version"] = package_version("ollama")
        report["code_commit"], report["working_tree_dirty"] = git_state()
        markdown = render_opaque_id_markdown(report, str(dataset_path))

    if args.format == "markdown":
        sys.stdout.write(markdown)
    else:
        json.dump(report, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
