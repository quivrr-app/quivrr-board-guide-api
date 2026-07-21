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

    def test_staged_catalogue_preserves_phase_three_counts_and_timmy_hold(self):
        rows = {row["manufacturer"]: row for row in list_manufacturers()}
        self.assertEqual((rows["Aloha Surfboards"]["model_count"], rows["Aloha Surfboards"]["standard_size_count"]), (8, 39))
        self.assertEqual((rows["AIPA Surf"]["model_count"], rows["AIPA Surf"]["standard_size_count"]), (5, 36))
        self.assertEqual((rows["Torq Surfboards"]["model_count"], rows["Torq Surfboards"]["standard_size_count"]), (14, 95))
        self.assertEqual(rows["Timmy Patterson Surfboards"]["lifecycle_state"], "canonical_pending")
        self.assertEqual(rows["Timmy Patterson Surfboards"]["model_count"], 0)

    def test_staged_models_keep_unknown_family_and_exact_construction_labels(self):
        torq = find_staged_model("Torq Surfboards", "Comp2")
        self.assertEqual(torq["public_family"], None)
        self.assertEqual(torq["family_evidence_status"], "missing_official_public_family_evidence")
        self.assertEqual(torq["constructions"], ["ACT", "TEC"])
        self.assertEqual(len(models_for_manufacturer("Aloha Surfboards")), 8)
        summaries = {row["manufacturer"]: row for row in construction_summaries()}
        self.assertEqual(summaries["AIPA Surf"]["constructions"], ["Carbon", "Dual-Core", "Fusion Pro", "Fusion-HD", "Tuflite"])

    def test_bodhi_can_read_factual_staged_record_without_promoting_a_family(self):
        record = find_board_record("Aloha Surfboards", "ALOHA LUNA")
        self.assertIsNotNone(record)
        self.assertTrue(record.unclassified)
        self.assertTrue(record.sizes)
        self.assertIsNone(record.primary_category)
        self.assertIn("official", record.source_type)

    def test_comparison_is_evidence_only_and_never_returns_a_performance_winner(self):
        left = find_staged_model("AIPA Surf", "Super Nova")
        right = find_staged_model("AIPA Surf", "Dark Horse")
        payload = compare_staged_models(left, right)
        self.assertEqual(payload["comparison_status"], "evidence_only_no_performance_ranking")
        self.assertIn("does not publish a performance winner", " ".join(payload["constraints"]))
        result = compare_board_models("AIPA Surf", "Super Nova", "AIPA Surf", "Dark Horse")
        self.assertIsNotNone(result)
        self.assertIsNone(result.left_fit)
        self.assertIn("will not rank", result.comparison.rider_specific_conclusion)

    def test_api_exposes_staged_catalogue_with_non_indexable_metadata(self):
        catalogue = self.client.get("/api/manufacturer-intelligence")
        self.assertEqual(catalogue.status_code, 200)
        self.assertEqual(catalogue.json()["catalogueState"], "staged_sql_pending")
        models = self.client.get("/api/manufacturer-intelligence/models", params={"brand": "Aloha Surfboards"})
        self.assertEqual(models.status_code, 200)
        self.assertEqual(len(models.json()["models"]), 8)
        self.assertFalse(models.json()["models"][0]["seo"]["indexable"])
        comparison = self.client.get("/api/manufacturer-intelligence/compare", params={
            "left_brand": "Torq Surfboards", "left_model": "Comp2",
            "right_brand": "Torq Surfboards", "right_model": "Go-Kart",
        })
        self.assertEqual(comparison.status_code, 200)
        self.assertEqual(comparison.json()["comparison_status"], "evidence_only_no_performance_ranking")


if __name__ == "__main__":
    unittest.main()
