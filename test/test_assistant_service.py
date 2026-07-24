import unittest
from unittest.mock import patch

from logic_layer.assistant_service import answer_medication_question


class FakeKG:
    def __init__(self):
        self.closed = False

    def check_safety(self, drug_names, user_conditions):
        return [
            {
                "type": "CONTRAINDICATION",
                "drug": drug_names[0],
                "condition": user_conditions[0],
                "reason": "测试风险",
                "severity": "RED",
            }
        ]

    def get_drug_info(self, drug_names):
        return [{"drug": drug_names[0], "function": "测试用途", "dosage": "测试剂量"}]

    def close(self):
        self.closed = True


class UnavailableKG(FakeKG):
    available = False


class FakeVectorStore:
    redis_client = object()

    def __init__(self):
        self.saved = None
        self.searched_session_id = None

    def get_conversation_context(self, query, session_id, top_k):
        self.searched_session_id = session_id
        return "【相关历史对话】\n1. 用户: 历史问题"

    def store_conversation(self, user_query, assistant_response, session_id):
        self.saved = (user_query, assistant_response, session_id)
        return True


class AssistantServiceTests(unittest.TestCase):
    def test_answer_medication_question_runs_kg_and_history_pipeline(self):
        kg = FakeKG()
        vector_store = FakeVectorStore()

        with patch("logic_layer.assistant_service.decide_tools", return_value="both"), \
             patch("logic_layer.assistant_service.exact_entity_extraction", return_value=(["泰诺"], ["饮酒状态"])), \
             patch("logic_layer.assistant_service.extract_entities_with_llm", return_value=([], [])), \
             patch("logic_layer.assistant_service.generate_safety_response", return_value="测试回答"):
            result = answer_medication_question(
                "喝酒后能吃泰诺吗？",
                session_id="test-session",
                vector_store=vector_store,
                kg=kg,
            )

        self.assertEqual(result["route"], "both")
        self.assertEqual(result["final_drugs"], ["泰诺"])
        self.assertEqual(result["final_conditions"], ["饮酒状态"])
        self.assertEqual(result["response_text"], "测试回答")
        self.assertTrue(result["conversation_saved"])
        self.assertEqual(vector_store.saved, ("喝酒后能吃泰诺吗？", "测试回答", "test-session"))
        self.assertFalse(kg.closed)

    def test_answer_medication_question_skips_kg_for_history_route(self):
        kg = FakeKG()
        vector_store = FakeVectorStore()

        with patch("logic_layer.assistant_service.decide_tools", return_value="search_history"), \
             patch("logic_layer.assistant_service.exact_entity_extraction") as exact_extract, \
             patch("logic_layer.assistant_service.extract_entities_with_llm") as llm_extract, \
             patch("logic_layer.assistant_service.generate_safety_response", return_value="历史回答"):
            result = answer_medication_question(
                "那还能继续吃吗？",
                vector_store=vector_store,
                kg=kg,
            )

        exact_extract.assert_not_called()
        llm_extract.assert_not_called()
        self.assertEqual(result["risks"], [])
        self.assertEqual(result["drug_infos"], [])
        self.assertEqual(result["response_text"], "历史回答")
        self.assertTrue(vector_store.searched_session_id)
        self.assertNotEqual(vector_store.searched_session_id, "shared")
        self.assertEqual(vector_store.saved[2], vector_store.searched_session_id)

    def test_prepare_medication_context_returns_metadata_without_generating_answer(self):
        from logic_layer.assistant_service import prepare_medication_context

        kg = FakeKG()
        vector_store = FakeVectorStore()

        with patch("logic_layer.assistant_service.decide_tools", return_value="both"), \
             patch("logic_layer.assistant_service.exact_entity_extraction", return_value=(["泰诺"], ["高血压"])), \
             patch("logic_layer.assistant_service.extract_entities_with_llm", return_value=([], [])), \
             patch("logic_layer.assistant_service.generate_safety_response") as generate:
            context = prepare_medication_context(
                "我有高血压，能吃泰诺吗？",
                session_id="test-session",
                vector_store=vector_store,
                kg=kg,
            )

        generate.assert_not_called()
        self.assertEqual(context["route"], "both")
        self.assertEqual(context["final_drugs"], ["泰诺"])
        self.assertEqual(context["final_conditions"], ["高血压"])
        self.assertEqual(context["risks"][0]["reason"], "测试风险")
        self.assertNotIn("response_text", context)

    def test_unavailable_kg_never_becomes_an_empty_safe_answer(self):
        kg = UnavailableKG()

        with patch("logic_layer.assistant_service.decide_tools", return_value="query_kg"), \
             patch("logic_layer.assistant_service.exact_entity_extraction", return_value=(["泰诺"], ["饮酒状态"])), \
             patch("logic_layer.assistant_service.extract_entities_with_llm", return_value=([], [])), \
             patch("logic_layer.assistant_service.generate_safety_response") as generate:
            result = answer_medication_question("泰诺能吃吗？", kg=kg)

        generate.assert_not_called()
        self.assertEqual(result["response_status"], "knowledge_unavailable")
        self.assertIn("未进行风险判断", result["response_text"])

    def test_save_conversation_result_records_success_and_failure(self):
        from logic_layer.assistant_service import save_conversation_result

        vector_store = FakeVectorStore()
        success = save_conversation_result(
            vector_store,
            "问题",
            "回答",
            "test-session",
        )

        self.assertTrue(success["conversation_saved"])
        self.assertIsNone(success["save_error"])
        self.assertEqual(vector_store.saved, ("问题", "回答", "test-session"))

        class FailingVectorStore(FakeVectorStore):
            def store_conversation(self, user_query, assistant_response, session_id):
                raise RuntimeError("redis offline")

        failure = save_conversation_result(
            FailingVectorStore(),
            "问题",
            "回答",
            "test-session",
        )

        self.assertFalse(failure["conversation_saved"])
        self.assertEqual(failure["save_error"], "conversation_store_unavailable")
        self.assertNotIn("redis offline", str(failure))

    def test_save_conversation_result_does_not_report_false_success(self):
        from logic_layer.assistant_service import save_conversation_result

        class RejectingVectorStore(FakeVectorStore):
            def store_conversation(self, user_query, assistant_response, session_id):
                return False

        result = save_conversation_result(
            RejectingVectorStore(),
            "问题",
            "回答",
            "test-session",
        )

        self.assertFalse(result["conversation_saved"])
        self.assertEqual(result["save_error"], "conversation_store_rejected")


if __name__ == "__main__":
    unittest.main()
