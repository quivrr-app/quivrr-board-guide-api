import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import main


class ConversationMemoryTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)

    @patch("main.enrich_suggestions_with_inventory", side_effect=lambda rows, profile: rows)
    def test_account_profile_and_conversation_profile_merge_across_turns(self, _inventory):
        first = self.client.post("/api/board-guide/chat", json={
            "message": "I'm advanced and surf 3 to 5ft reef breaks.",
            "account_profile": {"weight_kg": 79, "region": "EU", "ability": "Intermediate"},
        })
        self.assertEqual(first.status_code, 200)
        first_body = first.json()
        self.assertEqual(first_body["conversationProfile"]["weight_kg"], 79)
        self.assertEqual(first_body["conversationProfile"]["ability"], "Advanced")
        self.assertEqual(first_body["conversationProfile"]["region"], "EU")

        second = self.client.post("/api/board-guide/chat", json={
            "message": "I want more paddle in weaker surf.",
            "profile": first_body["conversationProfile"],
            "account_profile": {"weight_kg": 79, "region": "EU", "ability": "Intermediate"},
        })
        self.assertEqual(second.status_code, 200)
        second_body = second.json()
        self.assertEqual(second_body["conversationProfile"]["weight_kg"], 79)
        self.assertEqual(second_body["conversationProfile"]["wave_power"], "Weak")
        self.assertEqual(second_body["conversationProfile"]["region"], "EU")

    @patch("main.enrich_suggestions_with_inventory", side_effect=lambda rows, profile: rows)
    def test_response_exposes_profile_conflicts(self, _inventory):
        response = self.client.post("/api/board-guide/chat", json={
            "message": "Actually I surf reef breaks now.",
            "profile": {"wave_type": "Beach Break"},
        })
        body = response.json()
        self.assertTrue(any("wave_type:" in item for item in body["profileConflicts"]))

    @patch("main.enrich_suggestions_with_inventory", side_effect=lambda rows, profile: rows)
    def test_multi_turn_profile_build_and_weight_correction_keeps_latest_value(self, _inventory):
        first = self.client.post("/api/board-guide/chat", json={"message": "I weigh 75 kg."}).json()
        second = self.client.post("/api/board-guide/chat", json={
            "message": "I am intermediate.",
            "profile": first["conversationProfile"],
        }).json()
        third = self.client.post("/api/board-guide/chat", json={
            "message": "I normally surf 2 to 4 foot beach breaks.",
            "profile": second["conversationProfile"],
        }).json()
        fourth = self.client.post("/api/board-guide/chat", json={
            "message": "Actually, I am 78 kg now.",
            "profile": third["conversationProfile"],
        }).json()

        self.assertEqual(fourth["conversationProfile"]["weight_kg"], 78)
        self.assertFalse(any("weight_kg:" in item for item in fourth["profileConflicts"]))

    @patch("main.safe_ask_bodhi", return_value=(None, None))
    @patch("main.enrich_suggestions_with_inventory", side_effect=lambda rows, profile: rows)
    def test_fish_brief_survives_correction_explanation_and_indonesia_stock_follow_up(self, _inventory, _llm):
        first = self.client.post("/api/board-guide/chat", json={
            "message": "The Sampler is a hybrid shorty, not a fish.",
        }).json()
        self.assertEqual(first["conversationState"]["activeBoardBrief"]["public_family"], "daily_driver")

        second = self.client.post("/api/board-guide/chat", json={
            "message": "Explain what a fish is.",
            "conversationState": first["conversationState"],
        }).json()
        self.assertEqual(second["conversationState"]["activeBoardBrief"]["public_family"], "fish")

        third = self.client.post("/api/board-guide/chat", json={
            "message": "OK, what is in stock in Indo?",
            "conversationState": second["conversationState"],
        }).json()
        brief = third["conversationState"]["activeBoardBrief"]
        self.assertEqual(brief["public_family"], "fish")
        self.assertEqual(brief["region"], "ID")
        self.assertTrue(brief["stock_required"])
        self.assertTrue(all(board["category"] in {"Fish", "Performance Fish", "Traditional Fish", "Twin Fin", "Performance Twin"} for board in third["suggested_boards"]))

    def test_classification_correction_uses_governed_dna_without_mutating_it(self):
        response = self.client.post("/api/board-guide/chat", json={"message": "The El Patron is a step up."})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("step up", body["reply"].lower())
        self.assertEqual(body["conversationState"]["activeBoardBrief"]["public_family"], "step_up")


if __name__ == "__main__":
    unittest.main()
