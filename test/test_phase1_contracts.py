import unittest
import sys
import types
from unittest.mock import patch


class StubOllamaClient:
    def __init__(self, *args, **kwargs):
        pass

    def generate(self, *args, **kwargs):
        raise RuntimeError("stubbed ollama generate")

    def chat(self, *args, **kwargs):
        raise RuntimeError("stubbed ollama chat")


class StubGraphDatabase:
    @staticmethod
    def driver(*args, **kwargs):
        raise RuntimeError("stubbed neo4j driver")


if "ollama" not in sys.modules:
    ollama_stub = types.ModuleType("ollama")
    ollama_stub.Client = StubOllamaClient
    sys.modules["ollama"] = ollama_stub

if "neo4j" not in sys.modules:
    neo4j_stub = types.ModuleType("neo4j")
    neo4j_stub.GraphDatabase = StubGraphDatabase
    sys.modules["neo4j"] = neo4j_stub

if "dotenv" not in sys.modules:
    dotenv_stub = types.ModuleType("dotenv")
    dotenv_stub.load_dotenv = lambda *args, **kwargs: None
    sys.modules["dotenv"] = dotenv_stub

from logic_layer.entity_utils import exact_entity_extraction
from logic_layer.health_check import get_environment_diagnostics
from logic_layer.json_utils import parse_llm_json
from logic_layer.kg_service import MedicalKG
from logic_layer.llm_service import generate_safety_response
from logic_layer.router_service import decide_tools


class FakeSession:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def run(self, query, **kwargs):
        if "CONTAINS_INGREDIENT" in query and "drugs_with_ing" in query:
            return [
                {
                    "ingredient": "对乙酰氨基酚",
                    "drugs_with_ing": ["泰诺", "感康"],
                }
            ]
        if "INTERACTS_WITH" in query:
            return []
        if "CONTRAINDICATED_IN" in query:
            return []
        return []


class FakeDriver:
    def session(self):
        return FakeSession()


class Phase1ContractTests(unittest.TestCase):
    def test_parse_llm_json_accepts_markdown_fenced_json(self):
        data = parse_llm_json('```json\n{"route": "both"}\n```')

        self.assertEqual(data, {"route": "both"})

    def test_parse_llm_json_raises_for_invalid_json(self):
        with self.assertRaises(ValueError):
            parse_llm_json("route: both")

    def test_environment_diagnostics_reports_missing_neo4j_password(self):
        with patch("logic_layer.health_check.Config.NEO4J_PASSWORD", None):
            diagnostics = get_environment_diagnostics()

        self.assertFalse(diagnostics["ready"])
        self.assertIn("NEO4J_PASSWORD", diagnostics["missing"])
        self.assertFalse(diagnostics["services"]["neo4j"]["password_configured"])

    def test_environment_diagnostics_is_ready_when_required_config_exists(self):
        patches = [
            patch("logic_layer.health_check.Config.NEO4J_URI", "bolt://localhost:7687"),
            patch("logic_layer.health_check.Config.NEO4J_USER", "neo4j"),
            patch("logic_layer.health_check.Config.NEO4J_PASSWORD", "password"),
            patch("logic_layer.health_check.Config.OLLAMA_URL", "http://localhost:11434"),
            patch("logic_layer.health_check.Config.OLLAMA_MODEL", "deepseek-r1:7b"),
            patch("logic_layer.health_check.Config.REDIS_HOST", "localhost"),
        ]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)

        diagnostics = get_environment_diagnostics()

        self.assertTrue(diagnostics["ready"])
        self.assertEqual(diagnostics["missing"], [])

    def test_rule_entity_extraction_finds_drugs_and_conditions(self):
        drugs, conditions = exact_entity_extraction("我喝酒了，还能吃头孢和布洛芬吗？")

        self.assertIn("头孢拉定", drugs)
        self.assertIn("布洛芬缓释胶囊", drugs)
        self.assertIn("饮酒状态", conditions)

    def test_router_falls_back_to_both_when_llm_fails(self):
        with patch("logic_layer.router_service.ollama_client.generate", side_effect=RuntimeError("offline")):
            self.assertEqual(decide_tools("还能继续吃这个药吗？"), "both")

    def test_kg_duplicate_therapy_risk_has_common_fields(self):
        kg = MedicalKG.__new__(MedicalKG)
        kg.driver = FakeDriver()

        risks = kg.check_safety(["泰诺", "感康"], [])

        self.assertEqual(len(risks), 1)
        self.assertEqual(risks[0]["type"], "DUPLICATE_THERAPY")
        for key in ("drug", "condition", "reason", "severity"):
            self.assertIn(key, risks[0])

    def test_kg_check_safety_returns_empty_when_driver_unavailable(self):
        kg = MedicalKG.__new__(MedicalKG)
        kg.driver = None

        self.assertEqual(kg.check_safety(["泰诺"], ["饮酒状态"]), [])

    def test_generate_safety_response_accepts_complete_duplicate_therapy_risk(self):
        risks = [
            {
                "type": "DUPLICATE_THERAPY",
                "drug": "泰诺 + 感康",
                "condition": "药物过量",
                "ingredient": "对乙酰氨基酚",
                "reason": "均含有成分【对乙酰氨基酚】，叠加服用会导致肝肾损伤！",
                "severity": "FATAL",
            }
        ]

        with patch(
            "logic_layer.llm_service.ollama_client.chat",
            return_value={"message": {"content": "不要同时服用。"}},
        ):
            response = generate_safety_response("泰诺和感康能一起吃吗？", risks, [])

        self.assertIn("不要同时服用", response)

    def test_kg_duplicate_therapy_risk_matches_response_contract(self):
        kg = MedicalKG.__new__(MedicalKG)
        kg.driver = FakeDriver()

        risks = kg.check_safety(["泰诺", "感康"], [])

        self.assertIn("ingredient", risks[0])


if __name__ == "__main__":
    unittest.main()
