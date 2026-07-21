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

    def test_governed_models_keep_evidence_review_and_exact_construction_labels(self):
        torq = find_staged_model("Torq Surfboards", "Comp2")
        self.assertEqual(torq["public_family"], "performance_shortboard")
        self.assertEqual(torq["family_evidence_status"], "governed_official_source_review")
        self.assertEqual(torq["constructions"], ["ACT", "TEC"])
        self.assertEqual(len(models_for_manufacturer("Aloha Surfboards")), 8)
        summaries = {row["manufacturer"]: row for row in construction_summaries()}
        self.assertEqual(summaries["AIPA Surf"]["constructions"], ["Carbon", "Dual-Core", "Fusion Pro", "Fusion-HD", "Tuflite"])

    def test_bodhi_can_read_factual_staged_record_without_promoting_a_family(self):
        record = find_board_record("Aloha Surfboards", "ALOHA LUNA")
        self.assertIsNotNone(record)
        self.assertFalse(record.unclassified)
        self.assertTrue(record.sizes)
        self.assertEqual(record.primary_category, "performance_fish")
        self.assertEqual(record.source_type, "governed_board_master_phase3")

    def test_comparison_uses_governed_master_evidence_without_ride_test_claims(self):
        left = find_staged_model("AIPA Surf", "Super Nova")
        right = find_staged_model("AIPA Surf", "Dark Horse")
        payload = compare_staged_models(left, right)
        self.assertEqual(payload["comparison_status"], "governed_board_dna_comparison")
        self.assertIn("does not claim a first-hand", " ".join(payload["constraints"]))
        result = compare_board_models("AIPA Surf", "Super Nova", "AIPA Surf", "Dark Horse")
        self.assertIsNotNone(result)
        self.assertIsNotNone(result.left_fit)
        self.assertTrue(result.comparison.rider_specific_conclusion)

    def test_api_exposes_staged_catalogue_with_non_indexable_metadata(self):
        catalogue = self.client.get("/api/manufacturer-intelligence")
        self.assertEqual(catalogue.status_code, 200)
        self.assertEqual(catalogue.json()["catalogueState"], "accepted_sql_pending")
        models = self.client.get("/api/manufacturer-intelligence/models", params={"brand": "Aloha Surfboards"})
        self.assertEqual(models.status_code, 200)
        self.assertEqual(len(models.json()["models"]), 8)
        self.assertFalse(models.json()["models"][0]["seo"]["indexable"])
        comparison = self.client.get("/api/manufacturer-intelligence/compare", params={
            "left_brand": "Torq Surfboards", "left_model": "Comp2",
            "right_brand": "Torq Surfboards", "right_model": "Go-Kart",
        })
        self.assertEqual(comparison.status_code, 200)
        self.assertEqual(comparison.json()["comparison_status"], "governed_board_dna_comparison")

    def test_all_accepted_models_are_governed_in_the_board_master_and_timmy_is_not(self):
        from app.board_master import load_board_master

        master = load_board_master()["models"]
        promoted = [row for row in master if row["manufacturer"] in {"Aloha Surfboards", "AIPA Surf", "Torq Surfboards"}]
        self.assertEqual(len(promoted), 27)
        self.assertEqual({row["public_family"] for row in promoted} - {"fish", "groveller", "daily_driver", "performance_shortboard", "mid_length", "longboard"}, set())
        self.assertTrue(all(
            row["official_standard_sizes"]
            and row["official_url"].startswith("https://")
            and row["official_image_url"].startswith("https://")
            for row in promoted
        ))
        self.assertFalse(any(row["manufacturer"] == "Timmy Patterson Surfboards" for row in master))


if __name__ == "__main__":
    unittest.main()
