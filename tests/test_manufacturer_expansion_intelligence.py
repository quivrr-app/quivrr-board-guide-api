import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import main
from app.board_intelligence import find_board_record
from app.comparison_engine import compare_board_models
from app.manufacturer_intelligence import (
    canonical_manufacturer_name,
    compare_staged_models,
    construction_summaries,
    find_staged_model,
    list_manufacturers,
    models_for_manufacturer,
)
from app.models import SuggestedBoard


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

    def test_customer_aliases_resolve_to_canonical_manufacturers(self):
        self.assertEqual(canonical_manufacturer_name("Do you have AIPA surfboards?"), "AIPA Surf")
        self.assertEqual(canonical_manufacturer_name("Do you know T. Patterson?"), "Timmy Patterson Surfboards")

    def test_bodhi_answers_explicit_manufacturer_questions_before_generic_intake(self):
        aipa = self.client.post("/api/board-guide/chat", json={"message": "Do you have AIPA surfboards?"}).json()
        self.assertIn("31 AIPA models", aipa["reply"])
        self.assertEqual(aipa["conversationProfile"]["requested_brand"], "AIPA Surf")
        timmy = self.client.post("/api/board-guide/chat", json={"message": "Do you know Timmy Patterson?"}).json()
        self.assertIn("39 Timmy Patterson models", timmy["reply"])
        self.assertEqual(timmy["conversationProfile"]["requested_brand"], "Timmy Patterson Surfboards")

    def test_aipa_constraint_survives_rider_context_and_fish_follow_up(self):
        first = self.client.post("/api/board-guide/chat", json={"message": "Do you have AIPA surfboards?"}).json()
        second = self.client.post("/api/board-guide/chat", json={
            "message": "75kg, intermediate, point breaks",
            "profile": first["conversationProfile"],
            "conversationState": first["conversationState"],
        }).json()
        third = self.client.post("/api/board-guide/chat", json={
            "message": "I want a fish",
            "profile": second["conversationProfile"],
            "conversationState": second["conversationState"],
        }).json()
        self.assertEqual(third["conversationProfile"]["requested_brand"], "AIPA Surf")
        self.assertIn("kept your AIPA constraint", third["reply"])
        self.assertNotIn("Album", third["reply"])

    @patch("main.available_manufacturer_models")
    def test_aipa_stock_question_uses_regional_backend_summary(self, available_models):
        available_models.return_value = [SuggestedBoard(
            brand="AIPA Surf", model="Bonefish", category="Current regional stock",
            confidence=0.95, why_it_fits="Current regional inventory",
            available_count=3, retailer_count=1, availability_checked=True,
            availability_status="retailer_stock", region="AU", region_code="AU",
        )]
        body = self.client.post("/api/board-guide/chat", json={
            "message": "Do any AIPA boards have stock in Australia?",
        }).json()
        self.assertIn("3 currently available AIPA board listings", body["reply"])
        self.assertEqual(body["recommendations"][0]["brand"], "AIPA Surf")
        available_models.assert_called_once_with("AIPA Surf", "AU")

    def test_two_aipa_models_can_be_compared_without_invented_performance_rank(self):
        body = self.client.post("/api/board-guide/chat", json={
            "message": "Compare AIPA Bonefish and Dark Horse Pro",
        }).json()
        self.assertIsNotNone(body["comparison"])
        compared = {body["comparison"]["board_a"]["model"], body["comparison"]["board_b"]["model"]}
        self.assertEqual(compared, {"Bonefish", "Dark Horse Pro"})
        self.assertIn("will not rank", body["comparison"]["rider_specific_conclusion"])

    def test_bodhi_does_not_read_deferred_or_incomplete_models(self):
        record = find_board_record("Aloha Surfboards", "ALOHA LUNA")
        self.assertIsNone(record)
        self.assertIsNotNone(find_board_record("AIPA Surf", "Supernova"))

    def test_api_exposes_live_catalogue_with_indexable_metadata(self):
        catalogue = self.client.get("/api/manufacturer-intelligence")
        self.assertEqual(catalogue.status_code, 200)
        self.assertEqual(catalogue.json()["catalogueState"], "production_verified")
        models = self.client.get("/api/manufacturer-intelligence/models", params={"brand": "AIPA Surf"})
        self.assertEqual(models.status_code, 200)
        self.assertEqual(len(models.json()["models"]), 31)
        supernova = next(row for row in models.json()["models"] if row["model"] == "Supernova")
        self.assertTrue(supernova["seo"]["indexable"])
        self.assertIsNone(supernova["seo"]["reason"])
        self.assertEqual(supernova["seo"]["canonical_url"], "https://quivrr.surf/reviews/aipa-surf/supernova/")
        comparison = self.client.get("/api/manufacturer-intelligence/compare", params={
            "left_brand": "AIPA Surf", "left_model": "Supernova",
            "right_brand": "AIPA Surf", "right_model": "Dark Horse Pro",
        })
        self.assertEqual(comparison.status_code, 200)


if __name__ == "__main__":
    unittest.main()
