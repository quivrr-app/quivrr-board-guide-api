import unittest

from fastapi.testclient import TestClient

import main
from app.board_intelligence import find_board_record
from app.comparison_engine import compare_board_models
from app.manufacturer_intelligence import (
    compare_staged_models,
    construction_summaries,
    find_staged_model,
    list_manufacturers,
    models_for_manufacturer,
)


class ManufacturerExpansionIntelligenceTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)

    def test_active_rollout_is_aipa_and_timmy_pending_only(self):
        rows = {row["manufacturer"]: row for row in list_manufacturers()}
        self.assertEqual(set(rows), {"AIPA Surf", "Timmy Patterson Surfboards"})
        self.assertEqual((rows["AIPA Surf"]["model_count"], rows["AIPA Surf"]["standard_size_count"]), (0, 0))
        self.assertEqual(rows["AIPA Surf"]["lifecycle_state"], "canonical_pending")
        self.assertEqual(rows["Timmy Patterson Surfboards"]["lifecycle_state"], "canonical_pending")
        self.assertEqual(rows["Timmy Patterson Surfboards"]["model_count"], 0)

    def test_pending_catalogues_publish_no_models_or_constructions(self):
        self.assertIsNone(find_staged_model("AIPA Surf", "Super Nova"))
        self.assertEqual(models_for_manufacturer("AIPA Surf"), [])
        self.assertEqual(models_for_manufacturer("Timmy Patterson Surfboards"), [])
        summaries = {row["manufacturer"]: row for row in construction_summaries()}
        self.assertEqual(summaries["AIPA Surf"]["constructions"], [])
        self.assertEqual(summaries["Timmy Patterson Surfboards"]["constructions"], [])

    def test_bodhi_does_not_read_deferred_or_incomplete_models(self):
        record = find_board_record("Aloha Surfboards", "ALOHA LUNA")
        self.assertIsNone(record)
        self.assertIsNone(find_board_record("AIPA Surf", "Super Nova"))

    def test_api_exposes_staged_catalogue_with_non_indexable_metadata(self):
        catalogue = self.client.get("/api/manufacturer-intelligence")
        self.assertEqual(catalogue.status_code, 200)
        self.assertEqual(catalogue.json()["catalogueState"], "staged_sql_pending")
        models = self.client.get("/api/manufacturer-intelligence/models", params={"brand": "AIPA Surf"})
        self.assertEqual(models.status_code, 404)
        comparison = self.client.get("/api/manufacturer-intelligence/compare", params={
            "left_brand": "AIPA Surf", "left_model": "Super Nova",
            "right_brand": "AIPA Surf", "right_model": "Dark Horse",
        })
        self.assertEqual(comparison.status_code, 404)


if __name__ == "__main__":
    unittest.main()
