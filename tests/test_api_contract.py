import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import main
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
    def test_recommendation_and_availability_fields_remain_separate(self, inventory):
        inventory.return_value = [SuggestedBoard(
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
        )]
        response = self.client.post("/api/board-guide/chat", json={
            "message": "I am 75kg intermediate surfing 3 to 5ft beach breaks in the United States and want a daily driver.",
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


if __name__ == "__main__":
    unittest.main()
