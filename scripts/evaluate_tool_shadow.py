#!/usr/bin/env python3
"""Evaluate Ollama tool proposals without dispatching or executing any tool."""

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
from evaluation.tool_shadow import evaluate_tool_shadow, render_tool_shadow_markdown
from evaluation.tool_shadow_dataset import load_shadow_tool_cases
from medsafety.catalog import KnowledgeCatalog
from medsafety.entity_resolution import V1EntityResolver
from medsafety.explanation import EvidenceGroundedExplainer
from medsafety.safety_engine import SafetyEngine
from medsafety.tool_shadow_planner import OllamaToolShadowPlanner
from medsafety.tool_workflow import TypedSafetyWorkflow


DEFAULT_TOOL_MODEL = "qwen3:1.7b"


class ModelCapabilityError(ValueError):
    """Raised before evaluation when the model cannot accept tool schemas."""


def enforce_split_gate(split: str, allow_locked_test: bool) -> None:
    if split == "test" and not allow_locked_test:
        raise ValueError(
            "locked test split requires --allow-locked-test; preserve every result "
            "and do not tune this prompt version against it"
        )


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


def installed_model_metadata(planner: OllamaToolShadowPlanner) -> dict[str, object]:
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
        show_response = planner.client.show(planner.model)
        show_payload = (
            show_response
            if isinstance(show_response, dict)
            else show_response.model_dump(mode="json", exclude_none=True)
        )
        capabilities = sorted(show_payload.get("capabilities") or [])
        if "tools" not in capabilities:
            raise ModelCapabilityError(
                f"configured model lacks tools capability: {planner.model}"
            )
        return {
            "name": name,
            "digest": payload.get("digest"),
            "size_bytes": payload.get("size"),
            "modified_at": payload.get("modified_at"),
            "parameter_size": details.get("parameter_size"),
            "quantization_level": details.get("quantization_level"),
            "family": details.get("family"),
            "format": details.get("format"),
            "capabilities": capabilities,
        }
    raise ValueError(f"configured Ollama model is not installed: {planner.model}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default="eval/tool_shadow_v1.jsonl")
    parser.add_argument("--split", choices=("dev", "test"), default="dev")
    parser.add_argument("--allow-locked-test", action="store_true")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    parser.add_argument("--ollama-url", default=Config.OLLAMA_URL)
    parser.add_argument("--model", default=DEFAULT_TOOL_MODEL)
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument("--output")
    parser.add_argument("--records-output")
    args = parser.parse_args()

    try:
        enforce_split_gate(args.split, args.allow_locked_test)
    except ValueError as exc:
        parser.error(str(exc))
    if args.repetitions < 1:
        raise ValueError("repetitions must be positive")

    dataset_path = Path(args.dataset)
    cases = load_shadow_tool_cases(dataset_path, split=args.split)
    if not cases:
        raise ValueError(f"dataset contains no {args.split!r} cases")

    catalog = KnowledgeCatalog.from_directory(REPOSITORY_ROOT / "data/v1")
    workflow = TypedSafetyWorkflow(
        resolver=V1EntityResolver(catalog),
        engine=SafetyEngine(catalog),
        explainer=EvidenceGroundedExplainer(),
    )
    planner = OllamaToolShadowPlanner(
        host=args.ollama_url,
        model=args.model,
        timeout_seconds=args.timeout_seconds,
    )

    # Fail before a long evaluation if the service or configured model is absent.
    try:
        model_metadata = installed_model_metadata(planner)
    except ModelCapabilityError as exc:
        parser.error(str(exc))
    except Exception as exc:
        parser.error(
            "Ollama preflight failed "
            f"({type(exc).__name__}); start the service and verify --model"
        )
    report, records = evaluate_tool_shadow(
        cases,
        planner,
        workflow.registry.definitions(),
        repetitions=args.repetitions,
    )
    report["split"] = args.split
    report["dataset_sha256"] = hashlib.sha256(dataset_path.read_bytes()).hexdigest()
    report["model"] = model_metadata
    report["configured_model"] = args.model
    report["ollama_url"] = args.ollama_url
    report["ollama_package_version"] = package_version("ollama")
    report["code_commit"], report["working_tree_dirty"] = git_state()

    if args.records_output:
        records_path = Path(args.records_output)
        records_path.write_text(
            json.dumps(records, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    if args.format == "markdown":
        rendered_output = render_tool_shadow_markdown(report, str(dataset_path))
    else:
        rendered_output = (
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        )
    if args.output:
        Path(args.output).write_text(rendered_output, encoding="utf-8")
    else:
        sys.stdout.write(rendered_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
