import unittest

from logic_layer.embedding_service import EmbeddingService
from logic_layer.entity_utils import exact_entity_extraction, normalize_entity
from logic_layer.kg_service import MedicalKG
from logic_layer.llm_service import extract_entities_with_llm, generate_safety_response
from logic_layer.router_service import decide_tools
from logic_layer.vector_store import VectorStore


class PublicApiCompatibilityTests(unittest.TestCase):
    def test_existing_public_entry_points_are_preserved(self):
        public_entry_points = [
            EmbeddingService,
            exact_entity_extraction,
            normalize_entity,
            MedicalKG,
            extract_entities_with_llm,
            generate_safety_response,
            decide_tools,
            VectorStore,
        ]

        for entry_point in public_entry_points:
            self.assertTrue(callable(entry_point), entry_point)


if __name__ == "__main__":
    unittest.main()
