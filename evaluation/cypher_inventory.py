"""Parse the legacy Cypher fixture into an auditable source-completeness inventory."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


NODE_PATTERN = re.compile(
    r"CREATE\s+\((?P<variable>\w+):(?P<label>Drug|Ingredient|Condition)\s*\{(?P<body>.*?)\}\)",
    re.DOTALL,
)
RISK_PATTERN = re.compile(
    r"CREATE\s+\((?P<source>\w+)\)-\[:(?P<type>CONTRAINDICATED_IN|INTERACTS_WITH)\s*"
    r"\{(?P<body>.*?)\}\]->\((?P<target>\w+)\)",
    re.DOTALL,
)
PROPERTY_PATTERN = re.compile(r'(?P<key>\w+)\s*:\s*"(?P<value>(?:[^"\\]|\\.)*)"')


@dataclass(frozen=True)
class LegacyRiskFact:
    inventory_id: str
    relationship_type: str
    subject: str
    object: str
    severity: str
    source_label: str
    reason: str


def _properties(body: str) -> dict[str, str]:
    return {match.group("key"): match.group("value") for match in PROPERTY_PATTERN.finditer(body)}


def parse_legacy_risk_facts(path: str | Path) -> tuple[dict[str, str], list[LegacyRiskFact]]:
    text = Path(path).read_text(encoding="utf-8")
    names: dict[str, str] = {}
    for match in NODE_PATTERN.finditer(text):
        properties = _properties(match.group("body"))
        if properties.get("name"):
            names[match.group("variable")] = properties["name"]

    facts: list[LegacyRiskFact] = []
    seen_base_ids: dict[str, int] = {}
    for match in RISK_PATTERN.finditer(text):
        properties = _properties(match.group("body"))
        relation = match.group("type")
        source_variable = match.group("source")
        target_variable = match.group("target")
        base_id = f"legacy-{relation.lower()}-{source_variable}-{target_variable}"
        seen_base_ids[base_id] = seen_base_ids.get(base_id, 0) + 1
        suffix = f"-{seen_base_ids[base_id]:02d}" if seen_base_ids[base_id] > 1 else ""
        facts.append(
            LegacyRiskFact(
                inventory_id=base_id + suffix,
                relationship_type=relation,
                subject=names.get(source_variable, source_variable),
                object=names.get(target_variable, target_variable),
                severity=properties.get("severity", "MISSING"),
                source_label=properties.get("source", "MISSING"),
                reason=properties.get("reason", "MISSING"),
            )
        )
    return names, facts


def render_inventory_markdown(path: str | Path) -> str:
    names, facts = parse_legacy_risk_facts(path)
    contraindications = sum(f.relationship_type == "CONTRAINDICATED_IN" for f in facts)
    interactions = sum(f.relationship_type == "INTERACTS_WITH" for f in facts)
    lines = [
        "# Legacy Fact and Source Inventory",
        "",
        "Generated from `data_layer/medical_graph.cypher.txt` without changing its content.",
        "",
        "## Summary",
        "",
        f"- Named Drug/Ingredient/Condition nodes parsed: {len(names)}",
        f"- Contraindication facts: {contraindications}",
        f"- Interaction facts: {interactions}",
        f"- Total risk facts: {len(facts)}",
        f"- Facts with a verifiable URL and locator: 0/{len(facts)}",
        "- Review status: all `legacy_unreviewed`",
        "",
        "A source label is not treated as a verified citation. Every row is missing a source registry ID, URL, precise locator, access date, and reviewer record.",
        "",
        "## Facts",
        "",
        "| Inventory ID | Type | Subject | Object | Severity | Current source label | Missing metadata |",
        "|---|---|---|---|---|---|---|",
    ]
    for fact in facts:
        source_label = fact.source_label.replace("|", "\\|")
        lines.append(
            f"| `{fact.inventory_id}` | {fact.relationship_type} | {fact.subject} | {fact.object} | "
            f"{fact.severity} | {source_label} | source_id, URL, locator, accessed_at, reviewer |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "This inventory records what the repository currently claims; it does not endorse those claims. Facts may only move from `legacy_unreviewed` to `source_aligned` after their wording, scope, severity, and source locator are checked. Clinical review is a separate status.",
        ]
    )
    return "\n".join(lines) + "\n"
