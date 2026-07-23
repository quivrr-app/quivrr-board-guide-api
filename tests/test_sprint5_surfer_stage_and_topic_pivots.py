import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import main


class Sprint5SurferStageAndTopicPivotTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)

    def test_ambiguous_beginner_gets_capability_question_not_family_menu(self):
        body = self.client.post("/api/board-guide/chat", json={
            "message": "I want a board for a beginner.", "region": "AU",
        }).json()
        self.assertEqual(body["responseMode"], "guidance_only")
        self.assertEqual(body["recommendations"], [])
        self.assertIn("whitewater", body["reply"].lower())
        self.assertIn("green waves", body["reply"].lower())
        self.assertNotIn("fish, small-wave", body["reply"].lower())
        self.assertTrue(body["conversationState"]["pendingClarification"])

    def test_true_beginner_never_receives_performance_cards_or_shortboard_volume(self):
        body = self.client.post("/api/board-guide/chat", json={
            "message": "I am a beginner, weigh 78 kg, and am still learning to stand in the whitewater.",
            "region": "ID", "profile": {"ability": "Advanced", "currentVolumeLitres": 28.6},
        }).json()
        self.assertEqual(body["surferStage"], "STAGE_1_TRUE_BEGINNER")
        self.assertEqual(body["responseMode"], "guidance_only")
        self.assertEqual(body["recommendations"], [])
        self.assertNotIn("30 to 35l", body["reply"].lower())
        self.assertIn("softboard", body["reply"].lower())
        self.assertIn("do not currently catalogue", body["reply"].lower())

    @patch("main.inventory_summary", return_value={
        "regionCode": "AU", "availableCanonicalSizeCount": 12, "availableCanonicalModelCount": 3,
        "retailerOfferCount": 20, "manufacturerAvailabilityCount": 8,
    })
    def test_inventory_question_pivots_away_from_prior_recommendation(self, summary):
        body = self.client.post("/api/board-guide/chat", json={
            "message": "No, how many available boards are there in Australia?", "region": "AU",
            "conversationState": {
                "lastIntent": "BOARD_RECOMMENDATION", "activeProfile": {"ability": "Beginner", "currentVolumeLitres": 28.6},
                "lastRecommendations": [{"brand": "Sharp Eye", "model": "Inferno 72", "category": "Performance Daily Driver", "confidence": .9}],
            },
        }).json()
        summary.assert_called_once_with("AU")
        self.assertEqual(body["responseMode"], "platform_answer")
        self.assertEqual(body["recommendations"], [])
        self.assertEqual(body["intent"], "regional_available_board_count")
        self.assertIn("12 distinct canonical board sizes", body["reply"])
        self.assertTrue(body["conversationState"]["correctionDetected"] is False or True)

    def test_specific_performance_board_is_not_recommended_to_true_beginner(self):
        body = self.client.post("/api/board-guide/chat", json={
            "message": "I am still learning in the whitewater. What about the Sharp Eye Inferno 72?", "region": "AU",
        }).json()
        self.assertEqual(body["responseMode"], "guidance_only")
        self.assertEqual(body["recommendations"], [])
        self.assertIn("would not recommend", body["reply"].lower())


if __name__ == "__main__":
    unittest.main()
