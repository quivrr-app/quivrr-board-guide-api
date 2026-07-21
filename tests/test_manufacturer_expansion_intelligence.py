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

    def test_active_rollout_contains_only_owner_approved_aipa_and_timmy(self):
        rows = {row["manufacturer"]: row for row in list_manufacturers()}
        self.assertEqual(set(rows), {"AIPA Surf", "Timmy Patterson Surfboards"})
        self.assertEqual((rows["AIPA Surf"]["model_count"], rows["AIPA Surf"]["standard_size_count"]), (31, 799))
        self.assertEqual(rows["AIPA Surf"]["lifecycle_state"], "production_verified")
        self.assertEqual(rows["Timmy Patterson Surfboards"]["lifecycle_state"], "production_verified")
        self.assertEqual((rows["Timmy Patterson Surfboards"]["model_count"], rows["Timmy Patterson Surfboards"]["standard_size_count"]), (39, 640))

    def test_approved_catalogues_publish_models_and_constructions(self):
        self.assertIsNotNone(find_staged_model("AIPA Surf", "Supernova"))
        self.assertEqual(len(models_for_manufacturer("AIPA Surf")), 31)
        self.assertEqual(len(models_for_manufacturer("Timmy Patterson Surfboards")), 39)
        summaries = {row["manufacturer"]: row for row in construction_summaries()}
        self.assertIn("PU", summaries["AIPA Surf"]["constructions"])
        self.assertEqual(summaries["Timmy Patterson Surfboards"]["constructions"], ["EPS Epoxy", "PU", "Stringerless EPS"])

    def test_bodhi_does_not_read_deferred_or_incomplete_models(self):
        record = find_board_record("Aloha Surfboards", "ALOHA LUNA")
        self.assertIsNone(record)
        self.assertIsNotNone(find_board_record("AIPA Surf", "Supernova"))

    def test_api_exposes_release_ready_catalogue_with_non_indexable_metadata(self):
        catalogue = self.client.get("/api/manufacturer-intelligence")
        self.assertEqual(catalogue.status_code, 200)
        self.assertEqual(catalogue.json()["catalogueState"], "production_verified")
        models = self.client.get("/api/manufacturer-intelligence/models", params={"brand": "AIPA Surf"})
        self.assertEqual(models.status_code, 200)
        self.assertEqual(len(models.json()["models"]), 31)
        comparison = self.client.get("/api/manufacturer-intelligence/compare", params={
            "left_brand": "AIPA Surf", "left_model": "Supernova",
            "right_brand": "AIPA Surf", "right_model": "Dark Horse Pro",
        })
        self.assertEqual(comparison.status_code, 200)


if __name__ == "__main__":
    unittest.main()
