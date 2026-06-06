import unittest

from logic_layer.kg_service import MedicalKG


class FakeSession:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def run(self, query, **kwargs):
        return [
            {
                "labels": ["Drug"],
                "name": "布洛芬",
                "dosage": "按说明书",
                "category": "解热镇痛",
                "function": "退热止痛",
                "desc": None,
                "ingredients": ["布洛芬"],
            }
        ]


class FakeDriver:
    def session(self):
        return FakeSession()


class MedicalKGTests(unittest.TestCase):
    def test_get_drug_info_returns_empty_without_driver_or_drug_names(self):
        kg = MedicalKG.__new__(MedicalKG)
        kg.driver = None

        self.assertEqual(kg.get_drug_info(["布洛芬"]), [])
        self.assertEqual(kg.get_drug_info([]), [])

    def test_get_drug_info_maps_drug_records_without_live_neo4j(self):
        kg = MedicalKG.__new__(MedicalKG)
        kg.driver = FakeDriver()

        infos = kg.get_drug_info(["布洛芬"])

        self.assertEqual(
            infos,
            [
                {
                    "drug": "布洛芬",
                    "category": "解热镇痛",
                    "function": "退热止痛",
                    "dosage": "按说明书",
                    "ingredients": "布洛芬",
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
