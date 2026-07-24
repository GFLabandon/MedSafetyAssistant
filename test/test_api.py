import asyncio
import json
import unittest
from types import SimpleNamespace
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

    def test_query_request_defaults_to_unique_session_ids(self):
        from api import QueryRequest

        first = QueryRequest(question="第一位用户")
        second = QueryRequest(question="第二位用户")

        self.assertTrue(first.session_id)
        self.assertTrue(second.session_id)
        self.assertNotEqual(first.session_id, second.session_id)
        self.assertNotEqual(first.session_id, "shared")

    def test_query_request_replaces_blank_session_id(self):
        from api import QueryRequest

        request = QueryRequest(question="测试", session_id="   ")

        self.assertTrue(request.session_id)
        self.assertNotEqual(request.session_id, "shared")

    def test_query_request_rejects_session_key_metacharacters(self):
        from pydantic import ValidationError
        from api import QueryRequest

        with self.assertRaises(ValidationError):
            QueryRequest(question="测试", session_id="user:*")

    def test_clear_session_has_stable_success_and_unavailable_contracts(self):
        from api import clear_conversation_session

        store = unittest.mock.Mock()
        store.available = True
        store.clear_session.return_value = 3
        with patch("api.get_vector_store", return_value=store):
            success = asyncio.run(clear_conversation_session("session-a"))

        self.assertEqual(success["session_id"], "session-a")
        self.assertEqual(success["deleted_keys"], 3)

        with patch("api.get_vector_store", return_value=None):
            unavailable = asyncio.run(clear_conversation_session("session-a"))

        payload = json.loads(unavailable.body)
        self.assertEqual(unavailable.status_code, 503)
        self.assertEqual(payload["error"], "session_store_unavailable")
        self.assertNotIn("Redis", payload["detail"])

    def test_health_returns_environment_diagnostics(self):
        from api import health

        fake_diagnostics = {
            "ready": True,
            "status": "degraded",
            "services": {"ollama": {"ready": True}},
        }
        with patch("api.get_readiness_diagnostics", return_value=fake_diagnostics):
            response = asyncio.run(health())

        self.assertEqual(response, fake_diagnostics)

    def test_liveness_does_not_probe_external_dependencies(self):
        from api import live

        with patch(
            "api.get_liveness_diagnostics",
            return_value={"status": "alive"},
        ) as diagnostic:
            response = asyncio.run(live())

        self.assertEqual(response, {"status": "alive"})
        diagnostic.assert_called_once_with()

    def test_request_middleware_preserves_valid_id_and_sets_response_header(self):
        from starlette.responses import Response
        from api import request_observability

        request = SimpleNamespace(
            headers={"X-Request-ID": "client-request-001"},
            state=SimpleNamespace(),
            method="POST",
            url=SimpleNamespace(path="/api/v1/query"),
        )

        async def call_next(received_request):
            self.assertEqual(
                received_request.state.request_id,
                "client-request-001",
            )
            return Response(status_code=200)

        response = asyncio.run(request_observability(request, call_next))

        self.assertEqual(response.headers["X-Request-ID"], "client-request-001")

    def test_request_middleware_replaces_invalid_id(self):
        from starlette.responses import Response
        from api import request_observability

        request = SimpleNamespace(
            headers={"X-Request-ID": "invalid request id with spaces"},
            state=SimpleNamespace(),
            method="GET",
            url=SimpleNamespace(path="/api/live"),
        )

        async def call_next(received_request):
            return Response(status_code=200)

        response = asyncio.run(request_observability(request, call_next))

        self.assertNotEqual(
            response.headers["X-Request-ID"],
            "invalid request id with spaces",
        )
        self.assertTrue(response.headers["X-Request-ID"])

    def test_v1_safety_check_returns_source_aligned_evidence(self):
        from api import SafetyCheckRequest, check_v1_safety

        response = asyncio.run(
            check_v1_safety(SafetyCheckRequest(medications=["泰诺", "感康"]))
        )

        self.assertEqual(response["conclusion_status"], "risk_found")
        self.assertEqual(response["facts"][0]["fact_id"], "fact-duplicate-acetaminophen-001")
        self.assertIn("source-fda-acetaminophen-2025", response["facts"][0]["source_ids"])

    def test_v1_safety_check_rejects_blank_medication_list(self):
        from pydantic import ValidationError
        from api import SafetyCheckRequest

        with self.assertRaises(ValidationError):
            SafetyCheckRequest(medications=[" "])

    def test_v1_safety_check_returns_explicit_contraindication_context(self):
        from api import SafetyCheckRequest, check_v1_safety

        response = asyncio.run(
            check_v1_safety(
                SafetyCheckRequest(medications=["布洛芬"], contexts=["NSAID过敏"])
            )
        )

        self.assertEqual(response["conclusion_status"], "risk_found")
        self.assertEqual(
            response["facts"][0]["fact_id"],
            "fact-contraindication-ibuprofen-nsaid-allergic-reaction-001",
        )
        self.assertEqual(
            response["resolved_contexts"],
            ["服用阿司匹林或其他NSAID后出现哮喘、荨麻疹或过敏反应"],
        )

    def test_v1_safety_check_serializes_knowledge_unavailable(self):
        from api import SafetyCheckRequest, check_v1_safety
        from medsafety.contracts import ConclusionStatus, EvidencePacket

        unavailable = EvidencePacket(
            conclusion_status=ConclusionStatus.KNOWLEDGE_UNAVAILABLE,
            limitations=["用药安全知识库当前不可用，系统未进行风险判断，请稍后重试。"],
        )
        engine = unittest.mock.Mock()
        engine.assess.return_value = unavailable

        with patch("api.get_safety_engine", return_value=engine):
            response = asyncio.run(
                check_v1_safety(SafetyCheckRequest(medications=["泰诺"]))
            )

        self.assertEqual(response["conclusion_status"], "knowledge_unavailable")
        self.assertIsNone(response["data_version"])
        self.assertEqual(response["facts"], [])

    def test_v1_safety_explain_returns_extractively_grounded_claim(self):
        from api import SafetyExplainRequest, explain_v1_safety
        from medsafety.explanation import EvidenceGroundedExplainer

        with patch(
            "api.get_safety_explainer",
            return_value=EvidenceGroundedExplainer(),
        ):
            response = asyncio.run(
                explain_v1_safety(
                    SafetyExplainRequest(
                        medications=["泰诺", "感康"],
                        use_llm_plan=False,
                    )
                )
            )

        self.assertEqual(response["conclusion_status"], "risk_found")
        self.assertEqual(response["generation_mode"], "deterministic")
        self.assertEqual(
            response["claims"][0]["fact_id"],
            "fact-duplicate-acetaminophen-001",
        )
        self.assertIn("source-fda-acetaminophen-2025", response["claims"][0]["source_ids"])
        self.assertNotIn("facts", response)

    def test_unhandled_error_does_not_expose_exception_or_traceback(self):
        from api import unhandled_exception_handler

        response = asyncio.run(
            unhandled_exception_handler(None, RuntimeError("private connection detail"))
        )
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 500)
        self.assertEqual(payload["error"], "internal_server_error")
        self.assertNotIn("private connection detail", response.body.decode())
        self.assertNotIn("Traceback", response.body.decode())

    def test_stream_query_events_emit_meta_tokens_done_and_save_status(self):
        from api import QueryRequest, stream_query_events

        context = dict(SAMPLE_RESULT)
        context.pop("response_text")
        context.pop("conversation_saved")
        context.pop("save_error")

        with patch("api.MedicalKG") as kg_class, \
             patch("api.prepare_medication_context", return_value=context), \
             patch("api.stream_safety_response", return_value=iter(["结论", "：不要"])), \
             patch("api.save_conversation_result", return_value={"conversation_saved": True, "save_error": None}):
            kg_class.return_value.close.return_value = None
            events = list(stream_query_events(QueryRequest(question="问题", session_id="s1"), vector_store=None))

        self.assertIn('"type": "meta"', events[0])
        self.assertIn('"route": "both"', events[0])
        self.assertIn('"type": "token"', events[1])
        self.assertIn("结论", events[1])
        self.assertIn('"type": "token"', events[2])
        self.assertIn("：不要", events[2])
        self.assertIn('"type": "done"', events[3])
        self.assertIn('"conversation_saved": true', events[3])


if __name__ == "__main__":
    unittest.main()
