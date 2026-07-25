#!/usr/bin/env python3
"""Capture bounded EXPLAIN/PROFILE evidence for the P2 Neo4j read model."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from neo4j import GraphDatabase
from neo4j.exceptions import DriverError, Neo4jError

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from config import Config
from medsafety.catalog import KnowledgeCatalog
from medsafety.neo4j_query_plans import (
    QueryPlanEvidenceError,
    collect_query_plan_evidence,
    collect_safety_index_evidence,
)
from medsafety.neo4j_repository import Neo4jProjectionAuditor


def current_git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPOSITORY_ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unavailable"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capture read-only Neo4j query plans without changing the projection."
    )
    parser.add_argument("--data-dir", type=Path, default=REPOSITORY_ROOT / "data/v1")
    parser.add_argument("--database", default=Config.NEO4J_DATABASE)
    parser.add_argument(
        "--mode",
        choices=("EXPLAIN", "PROFILE"),
        default="PROFILE",
        help="PROFILE executes only the registered read queries; EXPLAIN does not execute them.",
    )
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not Config.NEO4J_PASSWORD:
        print("NEO4J_PASSWORD is required; no plan query was attempted.", file=sys.stderr)
        return 2

    catalog = KnowledgeCatalog.from_directory(args.data_dir)
    driver = GraphDatabase.driver(
        Config.NEO4J_URI,
        auth=(Config.NEO4J_USER, Config.NEO4J_PASSWORD),
        connection_timeout=Config.NEO4J_CONNECTION_TIMEOUT_SECONDS,
        connection_acquisition_timeout=Config.NEO4J_CONNECTION_TIMEOUT_SECONDS,
    )
    try:
        try:
            driver.verify_connectivity()
            neo4j_agent = driver.get_server_info().agent
            integrity = Neo4jProjectionAuditor(
                driver,
                database=args.database,
            ).audit(catalog)
            if not integrity.valid:
                print("Neo4j projection integrity check failed.", file=sys.stderr)
                return 4
            plans = collect_query_plan_evidence(
                driver,
                database=args.database,
                mode=args.mode,
            )
            indexes = collect_safety_index_evidence(
                driver,
                database=args.database,
            )
        except (DriverError, Neo4jError, QueryPlanEvidenceError) as exc:
            print(f"Neo4j plan capture failed: {type(exc).__name__}", file=sys.stderr)
            return 3
    finally:
        driver.close()

    payload = {
        "schema_version": "neo4j-query-plan-evidence-v1",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "code_commit": current_git_commit(),
        "neo4j_agent": neo4j_agent,
        "mode": args.mode,
        "data_version": catalog.data_version,
        "case_count": len(plans),
        "indexes": [asdict(item) for item in indexes],
        "cases": [asdict(item) | {"uses_index": item.uses_index} for item in plans],
        "limitations": [
            "The V1 graph is intentionally tiny; db_hits and timings are diagnostic, not a scalability benchmark.",
            "PROFILE executes only the registered read-only queries and does not mutate the projection.",
        ],
    }
    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(f"{rendered}\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
