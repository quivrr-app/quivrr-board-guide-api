import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import main
from app.inventory_client import quivrr_model_search_url, quivrr_search_url
from app.models import SuggestedBoard


class ApiContractTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)

    @patch("main.enrich_suggestions_with_inventory", side_effect=lambda rows, profile: rows)
    def test_response_includes_new_sprint4_contract_fields(self, _inventory):
        response = self.client.post("/api/board-guide/chat", json={
            "message": "75kg intermediate surfing 2 to 4ft beach breaks in Europe and want a daily driver.",
        })
        self.assertEqual(response.status_code, 200)
        body = response.json()

        self.assertIn("conversationProfile", body)
        self.assertIn("profileCompleteness", body)
        self.assertIn("profileConflicts", body)
        self.assertIn("profileLoaded", body)
        self.assertIn("profileAbilitySource", body)
        self.assertIn("profileVolumeSource", body)
        self.assertIn("profileWeightSource", body)
        self.assertIn("targetVolume", body)
        self.assertIn("volumeRecommendation", body)
        self.assertIn("usefulFollowUpQuestions", body)
        self.assertIn("recommendationVersion", body)
        self.assertIn("correlationId", body)
        self.assertEqual(body["recommendationVersion"], "bodhi-sprint-4")
        self.assertIn("guide_name", body)
        self.assertIn("reply", body)
        self.assertIn("profile", body)
        self.assertIn("recommendation", body)
        self.assertIn("suggested_boards", body)
        self.assertIn("missing_fields", body)
        self.assertIn("recommended_next_step", body)
        self.assertIn("source", body)
        self.assertIn("X-Correlation-ID", response.headers)
        self.assertEqual(body["correlationId"], response.headers["X-Correlation-ID"])

    @patch("main.enrich_suggestions_with_inventory")
    @patch("main.recommend_from_matrix")
    def test_recommendation_and_availability_fields_remain_separate(self, recommend_from_matrix, inventory):
        seeded = SuggestedBoard(
            brand="Pyzel",
            model="Phantom",
            category="Performance Daily Driver",
            confidence=0.91,
            fit_score=91,
            fit_confidence="high",
            why_it_fits="Drive and control",
            available_count=0,
            manufacturer_direct_count=0,
            retailer_count=0,
            availability_checked=True,
            availability_status="not_found",
            inventory_source=None,
            inventory_match_count=0,
            region="US",
            region_code="US",
        )
        recommend_from_matrix.return_value = [seeded]
        inventory.return_value = [seeded]
        response = self.client.post("/api/board-guide/chat", json={
            "message": "What should I ride next?",
            "profile": {
                "weight_kg": 75,
                "ability": "Intermediate",
                "region": "US",
                "wave_type": "Beach Break",
                "wave_size": "3-5ft",
                "preferred_board_type": "Daily Driver",
            },
        })
        self.assertEqual(response.status_code, 200)
        recommendation = response.json()["recommendations"][0]
        self.assertEqual(recommendation["fitScore"], 91)
        self.assertEqual(recommendation["fitConfidence"], "high")
        self.assertTrue(recommendation["availabilityChecked"])
        self.assertEqual(recommendation["availabilityStatus"], "not_found")
        self.assertEqual(recommendation["inventoryMatchCount"], 0)
        self.assertEqual(recommendation["regionCode"], "US")

    @patch("main.enrich_suggestions_with_inventory", side_effect=lambda rows, profile: rows)
    def test_request_accepts_profile_alias(self, _inventory):
        response = self.client.post("/api/board-guide/chat", json={
            "message": "Europe",
            "profile": {"weight_kg": 75, "ability": "Intermediate"},
        })
        body = response.json()
        self.assertEqual(body["conversationProfile"]["weight_kg"], 75)
        self.assertEqual(body["conversationProfile"]["region"], "EU")

    @patch("main.enrich_suggestions_with_inventory", side_effect=lambda rows, profile: rows)
    def test_inbound_correlation_id_is_preserved(self, _inventory):
        response = self.client.post(
            "/api/board-guide/chat",
            json={"message": "75kg intermediate in Europe"},
            headers={"X-Correlation-ID": "test-correlation-123"},
        )
        body = response.json()
        self.assertEqual(response.headers["X-Correlation-ID"], "test-correlation-123")
        self.assertEqual(body["correlationId"], "test-correlation-123")

    @patch("main.enrich_suggestions_with_inventory", side_effect=lambda rows, profile: rows)
    @patch("main.safe_ask_bodhi", return_value=(None, None))
    def test_openai_failure_keeps_valid_local_fallback(self, _safe_ask, _inventory):
        with patch.dict("os.environ", {"BODHI_ENABLE_LLM_REFINEMENT": "1"}):
            response = self.client.post("/api/board-guide/chat", json={
                "message": "75kg intermediate surfing 2 to 4ft beach breaks in Europe and want a daily driver.",
            })
        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(body["reply"], str)
        self.assertTrue(body["reply"])
        self.assertIsNone(body["modelDeployment"])

    def test_quivrr_model_search_urls_preselect_safely_for_each_region(self):
        board = SuggestedBoard(
            brand="Pyzel",
            model="Ghost",
            category="Performance shortboard",
            confidence=0.9,
            why_it_fits="Controlled test board",
        )
        expected = {
            "AU": "/australia?",
            "EU": "/europe?",
            "US": "/united-states?",
            "ID": "/indonesia?",
        }
        for region, path in expected.items():
            with self.subTest(region=region):
                url = quivrr_model_search_url(board, region)
                self.assertIn(path.replace("?", "/?"), url)
                self.assertIn("brand=Pyzel", url)
                self.assertIn("model=Ghost", url)
                self.assertNotIn("autoSearch=1", url)
                self.assertNotIn("construction=", url)
                self.assertNotIn("volume=", url)
                self.assertNotIn("boardSizeId=", url)

    def test_exact_size_search_url_only_autosearches_when_board_size_is_known(self):
        board = SuggestedBoard(
            brand="JS Industries",
            model="Monsta",
            category="Performance shortboard",
            confidence=0.9,
            why_it_fits="Controlled test board",
        )
        url = quivrr_search_url(board, "EU", {
            "construction": "CarboTune",
            "volumeLitres": 28,
            "boardSizeId": 123,
        })
        self.assertIn("autoSearch=1", url)
        self.assertIn("boardSizeId=123", url)


if __name__ == "__main__":
    unittest.main()
