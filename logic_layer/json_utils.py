import json


def parse_llm_json(content: str):
    """Parse JSON from an LLM response that may include markdown fences."""
    cleaned = content.strip().replace("```json", "").replace("```", "").strip()
    return json.loads(cleaned)
