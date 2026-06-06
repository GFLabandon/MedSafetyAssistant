import asyncio
import unittest
from unittest.mock import patch


SAMPLE_RESULT = {
    "route": "both",
    "history_context": "【相关历史对话】\n1. 用户: 我有高血压",
    "exact_drugs": ["泰诺"],
    "exact_conditions": ["高血压"],
    "llm_drugs": [],
    "llm_conditions": [],
    "final_drugs": ["泰诺"],
    "final_conditions": ["高血压"],
    "risks": [
        {
            "type": "CONTRAINDICATION",
            "drug": "泰诺",
            "condition": "高血压",
            "reason": "测试风险",
            "severity": "RED",
        }
    ],
    "drug_infos": [
        {
            "drug": "泰诺",
            "category": "解热镇痛",
            "function": "测试用途",
            "dosage": "测试剂量",
            "ingredients": "对乙酰氨基酚",
        }
    ],
    "response_text": "测试回答",
    "conversation_saved": True,
    "save_error": None,
}


class ApiContractTests(unittest.TestCase):
    def test_query_medication_returns_complete_service_contract(self):
        from api import QueryRequest, query_medication

        with patch("api.answer_medication_question", return_value=SAMPLE_RESULT) as service:
            response = asyncio.run(query_medication(QueryRequest(question="我有高血压，能吃泰诺吗？")))

        service.assert_called_once()
        self.assertEqual(response["route"], "both")
        self.assertEqual(response["response_text"], "测试回答")
        self.assertEqual(response["risks"][0]["type"], "CONTRAINDICATION")
        self.assertEqual(response["drug_infos"][0]["drug"], "泰诺")
        self.assertEqual(response["final_drugs"], ["泰诺"])
        self.assertTrue(response["conversation_saved"])

    def test_query_medication_rejects_blank_question(self):
        from pydantic import ValidationError
        from api import QueryRequest

        with self.assertRaises(ValidationError):
            QueryRequest(question="   ")

    def test_health_returns_environment_diagnostics(self):
        from api import health

        fake_diagnostics = {
            "ready": True,
            "missing": [],
            "services": {"ollama": {"ready": True}},
        }
        with patch("api.get_environment_diagnostics", return_value=fake_diagnostics):
            response = asyncio.run(health())

        self.assertEqual(response, fake_diagnostics)


if __name__ == "__main__":
    unittest.main()
