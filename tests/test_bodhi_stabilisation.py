import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import main


class BodhiStabilisationTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)

    def ask(self, message, **extra):
        response = self.client.post("/api/board-guide/chat", json={"message": message, **extra})
        response.raise_for_status()
        return response.json()

    def test_three_board_comparison_mentions_every_board(self):
        body = self.ask(
            "Compare Happy Everyday, Xero Gravity and Phantom for a 75kg surfer in average Australian beach breaks."
        )
        self.assertEqual(body["intent"], "comparison_request")
        for model in ("Happy Everyday", "Xero Gravity", "Phantom"):
            self.assertIn(model, body["reply"])
        self.assertNotIn("weight?", body["reply"].lower())
        self.assertEqual(body["recommendations"], [])

    def test_comparison_follow_up_retains_boards(self):
        body = self.ask(
            "I already told you my weight and region. Australia and I’m 75kg. So I’m looking around 28 litres.",
            conversation=[{
                "role": "user",
                "content": "Compare Happy Everyday, Xero Gravity and Phantom for a 75kg surfer in average Australian beach breaks.",
            }],
        )
        self.assertEqual(body["intent"], "comparison_request")
        for model in ("Happy Everyday", "Xero Gravity", "Phantom"):
            self.assertIn(model, body["reply"])
        for wrong in ("Hypto Krypto", "Churro 2", "Rare Bird"):
            self.assertNotIn(wrong, body["reply"])
        self.assertIn("around 28L", body["reply"])

    @patch("main.enrich_suggestions_with_inventory", side_effect=lambda rows, profile: [
        row.model_copy(update={"available_count": 1, "retailer_count": 1, "region": profile.region})
        for row in rows
    ])
    def test_advanced_performance_daily_driver_prioritises_correct_lane(self, _inventory):
        body = self.ask(
            "I’m 75kg, advanced, surfing Australian beach breaks 2-6ft. I want a performance daily driver, not a hybrid."
        )
        first = [row["model"].replace("-", " ").lower() for row in body["recommendations"][:5]]
        self.assertTrue(any(model in first for model in ["phantom", "xero gravity", "happy everyday", "inferno 72", "rad ripper"]))
        self.assertNotEqual(first[0], "hypto krypto")
        self.assertTrue(all(row["region"] == "AU" for row in body["recommendations"]))

    @patch("main.enrich_suggestions_with_inventory", side_effect=lambda rows, profile: [
        row.model_copy(update={"available_count": 1, "retailer_count": 1, "region": profile.region})
        for row in rows
    ])
    def test_monsta_pushback_explains_tradeoffs_and_checks_everyday_set(self, inventory):
        body = self.ask(
            "Monsta might be a bit aggressive for me. I’m looking more at an everyday board. Gravity or Happy Everyday.",
            region="AU",
            conversation=[{"role": "user", "content": "You suggested the JS Monsta for me."}],
        )
        self.assertIn("sharper, more demanding", body["reply"])
        self.assertIn("friendlier everyday shortboard", body["reply"])
        self.assertIn("Pyzel Phantom", body["reply"])
        checked = {row.model.replace("-", " ").lower() for row in inventory.call_args.args[0]}
        self.assertEqual(checked, {"xero gravity", "happy everyday", "phantom"})
        self.assertTrue(all(row["region"] == "AU" for row in body["recommendations"]))


if __name__ == "__main__":
    unittest.main()
