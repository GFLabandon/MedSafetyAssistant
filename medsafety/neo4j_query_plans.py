"""Read-only Neo4j query-plan evidence for the source-aligned projection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from medsafety.neo4j_repository import (
    _CONTRAINDICATION_FACTS,
    _DUPLICATE_FACT,
    _FACT_PROVENANCE,
    _INTERACTION_FACTS,
    _RESOLVE_CONTEXT,
    _RESOLVE_MEDICATION,
    _SNAPSHOT_NAME,
)


PlanMode = Literal["EXPLAIN", "PROFILE"]


@dataclass(frozen=True)
class QueryPlanCase:
    name: str
    query: str
    parameters: dict[str, Any]


@dataclass(frozen=True)
class QueryPlanEvidence:
    case_name: str
    mode: PlanMode
    query_type: str
    planner: str | None
    runtime: str | None
    operators: tuple[str, ...]
    index_details: tuple[str, ...]
    db_hits: int | None
    rows: int | None
    result_available_after_ms: int | None
    result_consumed_after_ms: int | None
    notification_codes: tuple[str, ...]

    @property
    def uses_index(self) -> bool:
        return bool(self.index_details)


@dataclass(frozen=True)
class IndexEvidence:
    name: str
    type: str
    entity_type: str
    labels_or_types: tuple[str, ...]
    properties: tuple[str, ...]
    state: str
    owning_constraint: str | None


class QueryPlanEvidenceError(RuntimeError):
    """Raised when Neo4j does not return a safe read-only plan."""


def default_query_plan_cases() -> tuple[QueryPlanCase, ...]:
    return (
        QueryPlanCase(
            name="resolve_medication",
            query=_RESOLVE_MEDICATION,
            parameters={"normalized_name": "泰诺"},
        ),
        QueryPlanCase(
            name="resolve_context",
            query=_RESOLVE_CONTEXT,
            parameters={"normalized_name": "nsaid过敏"},
        ),
        QueryPlanCase(
            name="duplicate_fact",
            query=_DUPLICATE_FACT,
            parameters={
                "ingredient": "对乙酰氨基酚",
                "snapshot_name": _SNAPSHOT_NAME,
            },
        ),
        QueryPlanCase(
            name="interaction_facts",
            query=_INTERACTION_FACTS,
            parameters={
                "left": ["布洛芬"],
                "right": ["阿司匹林"],
                "snapshot_name": _SNAPSHOT_NAME,
            },
        ),
        QueryPlanCase(
            name="contraindication_facts",
            query=_CONTRAINDICATION_FACTS,
            parameters={
                "ingredients": ["布洛芬"],
                "contexts": ["服用阿司匹林或其他NSAID后出现哮喘、荨麻疹或过敏反应"],
                "snapshot_name": _SNAPSHOT_NAME,
            },
        ),
        QueryPlanCase(
            name="fact_provenance",
            query=_FACT_PROVENANCE,
            parameters={
                "fact_id": "fact-duplicate-acetaminophen-001",
                "snapshot_name": _SNAPSHOT_NAME,
            },
        ),
    )


def _walk_plan(plan: dict[str, Any]) -> list[dict[str, Any]]:
    nodes = [plan]
    for child in plan.get("children", []):
        nodes.extend(_walk_plan(child))
    return nodes


def _operator_name(value: str) -> str:
    return value.split("@", 1)[0]


def collect_query_plan_evidence(
    driver: Any,
    *,
    database: str | None = None,
    mode: PlanMode = "PROFILE",
    cases: tuple[QueryPlanCase, ...] | None = None,
) -> list[QueryPlanEvidence]:
    if mode not in {"EXPLAIN", "PROFILE"}:
        raise ValueError("query plan mode must be EXPLAIN or PROFILE")

    observations: list[QueryPlanEvidence] = []
    with driver.session(database=database) as session:
        for case in cases or default_query_plan_cases():
            result = session.run(f"{mode} {case.query}", **case.parameters)
            if mode == "PROFILE":
                list(result)
            summary = result.consume()
            plan = summary.profile if mode == "PROFILE" else summary.plan
            if not isinstance(plan, dict):
                raise QueryPlanEvidenceError(f"{case.name} returned no {mode} plan")
            if summary.query_type != "r":
                raise QueryPlanEvidenceError(f"{case.name} is not read-only")

            nodes = _walk_plan(plan)
            operators = tuple(
                _operator_name(str(node.get("operatorType", "unknown")))
                for node in nodes
            )
            index_details = tuple(
                str(node.get("args", {}).get("Details", ""))
                for node in nodes
                if "Index" in str(node.get("operatorType", ""))
            )
            notifications = tuple(
                str(item.get("code", "unknown"))
                for item in (summary.notifications or [])
                if isinstance(item, dict)
            )
            root_args = plan.get("args", {})
            observations.append(
                QueryPlanEvidence(
                    case_name=case.name,
                    mode=mode,
                    query_type=summary.query_type,
                    planner=root_args.get("planner"),
                    runtime=root_args.get("runtime"),
                    operators=operators,
                    index_details=index_details,
                    db_hits=(
                        sum(int(node.get("dbHits", 0)) for node in nodes)
                        if mode == "PROFILE"
                        else None
                    ),
                    rows=int(plan.get("rows", 0)) if mode == "PROFILE" else None,
                    result_available_after_ms=summary.result_available_after,
                    result_consumed_after_ms=summary.result_consumed_after,
                    notification_codes=notifications,
                )
            )
    return observations


def collect_safety_index_evidence(
    driver: Any,
    *,
    database: str | None = None,
) -> list[IndexEvidence]:
    query = """
    SHOW INDEXES
    YIELD name, type, entityType, labelsOrTypes, properties, state, owningConstraint
    WHERE any(label IN labelsOrTypes WHERE label STARTS WITH 'Safety')
    RETURN name, type, entityType, labelsOrTypes, properties, state, owningConstraint
    ORDER BY name
    """
    with driver.session(database=database) as session:
        return [
            IndexEvidence(
                name=str(record["name"]),
                type=str(record["type"]),
                entity_type=str(record["entityType"]),
                labels_or_types=tuple(record["labelsOrTypes"]),
                properties=tuple(record["properties"]),
                state=str(record["state"]),
                owning_constraint=record["owningConstraint"],
            )
            for record in session.run(query)
        ]
