import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import main
from app.board_resolver import resolve_board


class BoardResolverTests(unittest.TestCase):
    def test_js_monsta_exact_and_safe_typo_resolution(self):
        exact = resolve_board("tell me about the JS monsta")
        self.assertEqual((exact.status, exact.brand, exact.model), ("resolved", "JS Industries", "Monsta"))
        self.assertEqual(exact.match_type, "exact_brand_and_model")

        typo = resolve_board("Tell me about the JS Mosta")
        self.assertEqual((typo.status, typo.brand, typo.model), ("resolved", "JS Industries", "Monsta"))
        self.assertIn(typo.match_type, {"alias_match", "fuzzy_model"})

    def test_suffix_stays_distinct(self):
        resolved = resolve_board("Tell me about the JS Monsta Easy Rider")
        self.assertEqual((resolved.brand, resolved.model), ("JS Industries", "Monsta Easy Rider"))


class BoardInformationApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)

    @patch("main.is_azure_openai_configured", return_value=False)
    def test_observed_monsta_conversation_does_not_fall_back(self, _azure):
        for message in ("tell me about the JS monsta", "I just did. Tell me about the JS Mosta", "JS monsta"):
            with self.subTest(message=message):
                body = self.client.post("/api/board-guide/chat", json={
                    "message": message,
                    "region": "ID",
                    "profile": {"region": "ID", "ability": "Advanced", "target_volume_litres": 28.6},
                }).json()
                self.assertEqual(body["intent"], "general_board_question")
                self.assertIn("JS Industries Monsta", body["reply"])
                self.assertNotIn("Ask me about a board type", body["reply"])

    @patch("main.is_azure_openai_configured", return_value=False)
    def test_contextual_suitability_comparison_and_unknown_model_fail_closed(self, _azure):
        first = self.client.post("/api/board-guide/chat", json={
            "message": "Tell me about the JS Monsta", "region": "ID",
            "profile": {"region": "ID", "ability": "Advanced", "target_volume_litres": 28.6},
        }).json()
        state = first["conversationState"]

        suitability = self.client.post("/api/board-guide/chat", json={
            "message": "Would it suit me?", "region": "ID", "conversationState": state,
            "profile": {"region": "ID", "ability": "Advanced", "target_volume_litres": 28.6},
        }).json()
        self.assertIn("JS Industries Monsta", suitability["reply"])
        self.assertNotIn("Tell me the source board", suitability["reply"])

        comparison = self.client.post("/api/board-guide/chat", json={
            "message": "Compare it with Xero Gravity", "region": "ID", "conversationState": state,
            "profile": {"region": "ID", "ability": "Advanced", "target_volume_litres": 28.6},
        }).json()
        self.assertIn("JS Industries Monsta", comparison["reply"])
        self.assertIn("JS Industries Xero Gravity", comparison["reply"])
        self.assertNotIn("Name the two boards", comparison["reply"])

        unknown = self.client.post("/api/board-guide/chat", json={
            "message": "Is an M23 suited to me?", "region": "ID", "conversationState": state,
            "profile": {"region": "ID", "ability": "Advanced", "target_volume_litres": 28.6},
        }).json()
        self.assertIn("can’t resolve that to a current canonical board model", unknown["reply"])
        self.assertNotIn("JS Industries Monsta is", unknown["reply"])


if __name__ == "__main__":
    unittest.main()
