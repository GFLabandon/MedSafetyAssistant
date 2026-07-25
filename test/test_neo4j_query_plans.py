from types import SimpleNamespace

import pytest

from medsafety.neo4j_query_plans import (
    QueryPlanCase,
    QueryPlanEvidenceError,
    collect_query_plan_evidence,
)


class FakeResult:
    def __init__(self, summary):
        self.summary = summary

    def __iter__(self):
        return iter([{"value": 1}])

    def consume(self):
        return self.summary


class FakeSession:
    def __init__(self, summary):
        self.summary = summary
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def run(self, query, **parameters):
        self.calls.append((query, parameters))
        return FakeResult(self.summary)


class FakeDriver:
    def __init__(self, summary):
        self.session_instance = FakeSession(summary)

    def session(self, database=None):
        assert database in (None, "neo4j")
        return self.session_instance


def _summary(query_type="r", profile=None):
    return SimpleNamespace(
        query_type=query_type,
        profile=profile,
        plan=None,
        notifications=[],
        result_available_after=2,
        result_consumed_after=3,
    )


def test_profile_evidence_collects_recursive_operators_and_index_details():
    profile = {
        "operatorType": "ProduceResults@neo4j",
        "args": {"planner": "COST", "runtime": "SLOTTED"},
        "dbHits": 1,
        "rows": 1,
        "children": [
            {
                "operatorType": "NodeUniqueIndexSeek@neo4j",
                "args": {"Details": "UNIQUE fact:SafetyFact(fact_id)"},
                "dbHits": 2,
                "rows": 1,
            }
        ],
    }
    driver = FakeDriver(_summary(profile=profile))
    cases = (QueryPlanCase("fact", "RETURN 1", {}),)

    evidence = collect_query_plan_evidence(
        driver,
        database="neo4j",
        cases=cases,
    )[0]

    assert evidence.operators == ("ProduceResults", "NodeUniqueIndexSeek")
    assert evidence.uses_index is True
    assert evidence.db_hits == 3
    assert evidence.rows == 1
    assert driver.session_instance.calls == [("PROFILE RETURN 1", {})]


def test_profile_evidence_rejects_non_read_queries():
    driver = FakeDriver(_summary(query_type="w", profile={"operatorType": "Create"}))

    with pytest.raises(QueryPlanEvidenceError, match="not read-only"):
        collect_query_plan_evidence(
            driver,
            cases=(QueryPlanCase("unsafe", "CREATE ()", {}),),
        )
