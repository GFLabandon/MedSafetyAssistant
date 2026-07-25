#!/usr/bin/env python3
"""Validate and upsert the canonical V1 catalog into Neo4j."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from neo4j import GraphDatabase
from neo4j.exceptions import DriverError, Neo4jError

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from config import Config
from medsafety.catalog import KnowledgeCatalog
from medsafety.neo4j_repository import (
    Neo4jCatalogImporter,
    Neo4jProjectionAuditor,
    ProjectionIntegrityError,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate data/v1 and upsert it into the Neo4j safety projection."
    )
    parser.add_argument("--data-dir", type=Path, default=REPOSITORY_ROOT / "data/v1")
    parser.add_argument("--database", default=Config.NEO4J_DATABASE)
    parser.add_argument(
        "--audit-only",
        action="store_true",
        help="inspect the existing Safety* projection without rebuilding it",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not Config.NEO4J_PASSWORD:
        print("NEO4J_PASSWORD is required; no import was attempted.", file=sys.stderr)
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
            if args.audit_only:
                summary = Neo4jProjectionAuditor(
                    driver,
                    database=args.database,
                ).audit(catalog)
            else:
                summary = Neo4jCatalogImporter(
                    driver,
                    database=args.database,
                ).import_catalog(catalog)
        except (DriverError, Neo4jError, ProjectionIntegrityError) as exc:
            print(f"Neo4j import failed: {type(exc).__name__}", file=sys.stderr)
            return 3
    finally:
        driver.close()

    payload = asdict(summary)
    if args.audit_only:
        payload["valid"] = summary.valid
        payload["issues"] = list(summary.issues)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if not args.audit_only or summary.valid else 4


if __name__ == "__main__":
    raise SystemExit(main())
