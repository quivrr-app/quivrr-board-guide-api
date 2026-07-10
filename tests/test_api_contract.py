import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import main


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
