import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import main
from app.intent_router import route_intent
from app.models import SuggestedBoard
from app.profile_engine import extract_profile


def live_fish_rows(_profile, _category):
    return [
        SuggestedBoard(
            brand="Album", model="Fascination", category="fish", confidence=.9,
            why_it_fits="fish profile near 30L", suggested_size="5'8 | 30L",
            available_count=3, retailer_count=3, region="EU",
            example_live_source_url="https://example.test/eu/album",
        ),
        SuggestedBoard(
            brand="JS Industries", model="Flame Fish", category="groveller", confidence=.86,
            why_it_fits="fish-style small-wave profile near 30L", suggested_size="5'7 | 30.2L",
            available_count=2, manufacturer_direct_count=2, region="EU",
            example_live_source_url="https://example.test/eu/js",
        ),
    ]


class IntentRouterTests(unittest.TestCase):
    def test_routes_supported_intents(self):
        cases = {
            "How many boards do you know about in Europe?": "inventory_count_question",
            "Show me fish boards around 30 litres in Europe": "board_search_request",
            "I need help choosing a board": "surfer_fit_request",
            "Xero Gravity is out of stock, what else is similar?": "alternative_request",
            "Compare Ghost and Phantom": "comparison_request",
            "What is a fish surfboard?": "general_board_question",
            "How do I use the site?": "site_help_question",
        }
        for message, expected in cases.items():
            with self.subTest(message=message):
                self.assertEqual(route_intent(message), expected)

    def test_natural_language_profile_extraction(self):
        profile = extract_profile(
            "I'm advanced and 75kgs, surf good reef breaks, want a daily driver and I'll be buying in Europe.",
            "Australia",
        )
        self.assertEqual(profile.weight_kg, 75)
        self.assertEqual(profile.ability, "Advanced")
        self.assertEqual(profile.preferred_board_type, "Daily Driver")
        self.assertEqual(profile.region, "EU")
        self.assertEqual(profile.wave_type, "Reef Break")
        self.assertEqual(profile.wave_power, "Average to Powerful")


class BodhiIntentApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)

    def test_inventory_count_does_not_trigger_intake(self):
        response = self.client.post("/api/board-guide/chat", json={
            "message": "How many boards do you know about in Europe?", "region": "Australia",
        })
        body = response.json()
        self.assertEqual(body["intent"], "inventory_count_question")
        self.assertEqual(body["intakeState"]["region"], "EU")
        self.assertIn("retailer listings", body["reply"])
        self.assertNotIn("rough weight", body["reply"].lower())

    @patch("main.search_live_category", side_effect=live_fish_rows)
    def test_fish_search_returns_live_eu_models(self, _search):
        response = self.client.post("/api/board-guide/chat", json={
            "message": "Show me fish boards around 30 litres in Europe", "region": "Australia",
        })
        body = response.json()
        self.assertEqual(body["intent"], "board_search_request")
        self.assertEqual(body["intakeState"]["target_volume_litres"], 30)
        self.assertEqual({row["brand"] for row in body["recommendations"]}, {"Album", "JS Industries"})
        self.assertTrue(all(row["region"] == "EU" for row in body["recommendations"]))
        self.assertNotIn("rough weight", body["reply"].lower())

    @patch("main.enrich_suggestions_with_inventory", side_effect=lambda rows, profile: [
        row.model_copy(update={"available_count": 1, "retailer_count": 1, "region": profile.region})
        for row in rows
    ])
    def test_complete_fit_recommends_before_follow_up(self, _inventory):
        response = self.client.post("/api/board-guide/chat", json={
            "message": "I'm advanced and 75kg, surf good waves and want a daily driver. I'll be buying in Europe.",
            "region": "Australia",
        })
        body = response.json()
        self.assertEqual(body["intakeState"]["weight_kg"], 75)
        self.assertEqual(body["intakeState"]["ability"], "Advanced")
        self.assertTrue(body["recommendations"])
        self.assertNotIn("rough weight", body["reply"].lower())
        self.assertNotIn("describe your surfing level", body["reply"].lower())

    def test_comparison_uses_canonical_graph(self):
        response = self.client.post("/api/board-guide/chat", json={
            "message": "Compare Pyzel Phantom and JS Monsta", "region": "EU",
        })
        body = response.json()
        self.assertEqual(body["intent"], "comparison_request")
        self.assertIn("Pyzel Phantom", body["reply"])
        self.assertIn("JS Industries Monsta", body["reply"])

    def test_site_help_does_not_start_fit_intake(self):
        response = self.client.post("/api/board-guide/chat", json={
            "message": "How do I use the site?", "region": "EU",
        })
        body = response.json()
        self.assertEqual(body["intent"], "site_help_question")
        self.assertIn("Start in the Europe search", body["reply"])
        self.assertEqual(body["missingQuestions"], [])


if __name__ == "__main__":
    unittest.main()
