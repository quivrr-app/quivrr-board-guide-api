import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import main
from app.authenticated_profile import AuthenticatedProfileContext
from app.models import RiderProfile


class BodhiApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)

    @patch("main.is_azure_openai_configured", return_value=False)
    @patch("main.enrich_suggestions_with_inventory", side_effect=lambda rows, _profile: rows)
    def test_28_litre_request_asks_one_useful_question(self, _inventory, _azure):
        response = self.client.post("/api/board-guide/chat", json={
            "message": "I want a new shortboard around 28 litres", "region": "EU",
        })
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["profile"]["target_volume_litres"], 28)
        self.assertIn("weight", body["reply"].lower())
        self.assertEqual(body["intakeState"]["preferred_board_type"], "Shortboard")
        self.assertLessEqual(len(body["missingQuestions"]), 2)

    @patch("main.is_azure_openai_configured", return_value=False)
    @patch("main.enrich_suggestions_with_inventory", side_effect=lambda rows, _profile: rows)
    def test_opening_greeting(self, _inventory, _azure):
        response = self.client.post("/api/board-guide/chat", json={"message": ""})
        self.assertIn("live board availability across Quivrr", response.json()["reply"])

    @patch("main.is_azure_openai_configured", return_value=False)
    @patch("main.enrich_suggestions_with_inventory", side_effect=lambda rows, _profile: rows)
    def test_region_aware_opening_greeting(self, _inventory, _azure):
        response = self.client.post("/api/board-guide/chat", json={"message": "", "region": "EU"})
        self.assertIn("live European board availability", response.json()["reply"])

    @patch("main.is_azure_openai_configured", return_value=False)
    @patch("main.enrich_suggestions_with_inventory", side_effect=lambda rows, _profile: rows)
    @patch("main.load_authenticated_profile_context")
    def test_authenticated_profile_personalises_first_reply(self, auth_loader, _inventory, _azure):
        auth_loader.return_value = AuthenticatedProfileContext(
            authenticated=True,
            profile_loaded=True,
            user_id="user-123",
            profile=RiderProfile(
                display_name="Nathan Dunn",
                weight_kg=78,
                ability="Advanced",
                region="ID",
                wave_type="Point Break",
                goal="Performance progression",
                preferred_brands=["JS Industries", "Album"],
            ),
        )
        response = self.client.post(
            "/api/board-guide/chat",
            json={"message": "Need a daily driver for 3-5ft surf"},
            headers={"Authorization": "Bearer token-123"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["reply"].startswith("Hey Nathan."))
        self.assertEqual(body["conversationProfile"]["region"], "ID")
        self.assertEqual(body["conversationProfile"]["ability"], "Advanced")

    @patch("main.is_azure_openai_configured", return_value=False)
    @patch("main.enrich_suggestions_with_inventory", side_effect=lambda rows, _profile: rows)
    @patch("main.load_authenticated_profile_context")
    def test_invalid_bearer_token_falls_back_to_anonymous_chat(self, auth_loader, _inventory, _azure):
        auth_loader.return_value = AuthenticatedProfileContext(
            authenticated=False,
            profile_loaded=False,
            invalid_token=True,
            profile=None,
        )
        response = self.client.post(
            "/api/board-guide/chat",
            json={"message": "Looking for a fish in Australia"},
            headers={"Authorization": "Bearer bad-token"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertNotIn("Nathan", body["reply"])
        self.assertEqual(body["conversationProfile"].get("display_name"), None)

    @patch("main.is_azure_openai_configured", return_value=False)
    @patch("main.enrich_suggestions_with_inventory", side_effect=lambda rows, _profile: rows)
    def test_conversation_merges_weight_skill_and_wave_follow_up(self, _inventory, _azure):
        response = self.client.post("/api/board-guide/chat", json={
            "message": "I am 75kg, intermediate, surfing beach breaks around 2-4ft twice a week",
            "region": "AU",
            "conversation": [{"role": "user", "content": "I want a shortboard around 28 litres"}],
        })
        body = response.json()
        self.assertEqual(body["intakeState"]["weight_kg"], 75)
        self.assertEqual(body["intakeState"]["target_volume_litres"], 28)
        self.assertEqual(body["intakeState"]["ability"], "Intermediate")
        self.assertIsNotNone(body["volumeGuidance"])
        self.assertIn("sensible starting range", body["reply"])

    @patch("main.is_azure_openai_configured", return_value=False)
    @patch("main.enrich_suggestions_with_inventory", side_effect=lambda rows, _profile: rows)
    def test_australia_good_or_average_profile_persists_without_reasking_skill(self, _inventory, _azure):
        first = self.client.post("/api/board-guide/chat", json={
            "message": "Im surfing in australia, am 75kgs, a good or average surfer, im 46 years old and 175cm high",
        })
        self.assertEqual(first.status_code, 200)
        first_body = first.json()
        state = first_body["intakeState"]
        self.assertEqual(state["region"], "AU")
        self.assertEqual(state["weight_kg"], 75)
        self.assertEqual(state["height_cm"], 175)
        self.assertEqual(state["age"], 46)
        self.assertEqual(state["ability"], "Intermediate")
        self.assertIn("29 to 33L", first_body["reply"])
        self.assertIn("27.5 to 30.5L", first_body["reply"])
        self.assertNotIn("surfing level", first_body["reply"].lower())

        second = self.client.post("/api/board-guide/chat", json={
            "message": "I just said im a good surfer or average. did you not see that?",
            "intakeState": state,
            "conversation": [
                {"role": "user", "content": "Im surfing in australia, am 75kgs, a good or average surfer, im 46 years old and 175cm high"},
                {"role": "assistant", "content": first_body["reply"]},
            ],
        })
        self.assertEqual(second.status_code, 200)
        second_body = second.json()
        self.assertEqual(second_body["intakeState"]["ability"], "Intermediate")
        self.assertIn("Yep, I’ve got that", second_body["reply"])
        self.assertIn("waves you usually surf", second_body["reply"])
        self.assertNotIn("surfing level", second_body["reply"].lower())

    @staticmethod
    def _regional_inventory(rows, profile):
        region = profile.region.upper()
        return [row.model_copy(update={
            "available_count": 2 if index == 0 else 0,
            "retailer_count": 2 if index == 0 else 0,
            "region": region,
            "example_live_source_url": f"https://example.test/{region.lower()}/{index}" if index == 0 else None,
        }) for index, row in enumerate(rows)]

    @patch("main.is_azure_openai_configured", return_value=False)
    @patch("main.enrich_suggestions_with_inventory", side_effect=_regional_inventory)
    def test_au_only_recommendation_shape(self, _inventory, _azure):
        response = self.client.post("/api/board-guide/chat", json={
            "message": "75kg intermediate, 2-4ft beach breaks twice a week, daily shortboard", "region": "AU",
        })
        boards = response.json()["recommendations"]
        self.assertTrue(boards)
        self.assertTrue(all(board["region"] == "AU" for board in boards))
        self.assertEqual(boards[0]["sourceType"], "retailer")

    @patch("main.is_azure_openai_configured", return_value=False)
    @patch("main.enrich_suggestions_with_inventory", side_effect=_regional_inventory)
    def test_eu_only_recommendation_shape(self, _inventory, _azure):
        response = self.client.post("/api/board-guide/chat", json={
            "message": "75kg intermediate, 2-4ft beach breaks twice a week, daily shortboard", "region": "EU",
        })
        boards = response.json()["recommendations"]
        self.assertTrue(boards)
        self.assertTrue(all(board["region"] == "EU" for board in boards))
        self.assertNotIn("/au/", (boards[0]["exampleProductUrl"] or "").lower())

    @staticmethod
    def _alternatives_inventory(rows, profile):
        requested = len(rows) == 1 and rows[0].model == "Xero Gravity"
        return [row.model_copy(update={
            "available_count": 0 if requested else (1 if index == 0 else 0),
            "retailer_count": 0 if requested else (1 if index == 0 else 0),
            "region": profile.region,
            "example_live_source_url": None if requested else f"https://example.test/{profile.region.lower()}/alternative",
        }) for index, row in enumerate(rows)]

    @patch("main.is_azure_openai_configured", return_value=False)
    @patch("main.enrich_suggestions_with_inventory", side_effect=_alternatives_inventory)
    def test_out_of_stock_uses_live_graph_alternative(self, _inventory, _azure):
        response = self.client.post("/api/board-guide/chat", json={
            "message": "Is the JS Xero Gravity available?", "region": "AU",
        })
        body = response.json()
        self.assertIn("can’t find", body["reply"].lower())
        self.assertTrue(body["recommendations"])
        self.assertTrue(all(board["availableCount"] > 0 for board in body["recommendations"]))
        self.assertTrue(all(board["region"] == "AU" for board in body["recommendations"]))

    @patch("main.is_azure_openai_configured", return_value=False)
    @patch("main.enrich_suggestions_with_inventory", side_effect=_regional_inventory)
    def test_current_board_upgrade_uses_graph(self, _inventory, _azure):
        response = self.client.post("/api/board-guide/chat", json={
            "message": "I ride a Hypto Krypto but want more performance. I am 75kg advanced, surf 3-6ft reef breaks twice a week.",
            "region": "EU",
        })
        body = response.json()
        self.assertIn("Hypto Krypto", body["intakeState"]["current_board"])
        self.assertTrue(body["suggested_boards"])
        self.assertTrue(any(board["category"] == "Performance Daily Driver" for board in body["suggested_boards"]))
        self.assertTrue(all(board["region"] == "EU" for board in body["suggested_boards"]))

    @patch("main.is_azure_openai_configured", return_value=False)
    @patch("main.enrich_suggestions_with_inventory", side_effect=lambda rows, profile: [
        row.model_copy(update={"region": profile.region, "available_count": 0}) for row in rows
    ])
    def test_no_hallucinated_stock(self, _inventory, _azure):
        response = self.client.post("/api/board-guide/chat", json={
            "message": "75kg intermediate, 2-4ft beach breaks twice a week", "region": "EU",
        })
        body = response.json()
        self.assertTrue(all(board["availableCount"] == 0 for board in body["recommendations"]))
        self.assertIn("won’t invent stock", body["reply"])

    @patch("main.is_azure_openai_configured", return_value=False)
    @patch("main.enrich_suggestions_with_inventory", side_effect=_regional_inventory)
    def test_three_turn_fish_intake_keeps_context_and_prioritises_point_break_fish(self, _inventory, _azure):
        first = self.client.post("/api/board-guide/chat", json={
            "message": "Good / average surfer, 46, fit, 76kg, looking for a good fish.",
        }).json()
        self.assertEqual(first["intakeState"]["ability"], "Intermediate")
        self.assertEqual(first["intakeState"]["preferred_board_type"], "Fish")
        self.assertIn("31 to 35L", first["reply"])
        self.assertIn("Which region", first["reply"])

        second = self.client.post("/api/board-guide/chat", json={
            "message": "Australia", "intakeState": first["intakeState"],
        }).json()
        self.assertEqual(second["intakeState"]["preferred_board_type"], "Fish")
        self.assertEqual(second["intakeState"]["region"], "AU")
        self.assertIn("weak beach breaks, points, or reefs", second["reply"])

        third = self.client.post("/api/board-guide/chat", json={
            "message": "point breaks", "intakeState": second["intakeState"],
        }).json()
        self.assertEqual(third["intakeState"]["preferred_board_type"], "Fish")
        self.assertIn("down-the-line fish", third["reply"])
        self.assertIn("Christenson Fish/Ocean Racer", third["reply"])
        self.assertIn("Album Lightbender", third["reply"])
        self.assertTrue(all(row["region"] == "AU" for row in third["recommendations"]))
        self.assertTrue(all(row["availableCount"] > 0 for row in third["recommendations"]))

    @patch("main.is_azure_openai_configured", return_value=False)
    @patch("main.enrich_suggestions_with_inventory", side_effect=lambda rows, profile: [
        row.model_copy(update={
            "available_count": 1 if index == 0 else 0,
            "retailer_count": 1 if index == 0 else 0,
            "region": profile.region,
        }) for index, row in enumerate(rows)
    ])
    def test_fish_reply_mentions_canonical_fits_even_when_not_live(self, _inventory, _azure):
        body = self.client.post("/api/board-guide/chat", json={
            "message": "76kg intermediate looking for a fish for point breaks in Australia",
        }).json()
        self.assertIn("canonical boards", body["reply"])
        self.assertIn("not currently found in live stock", body["reply"])
        self.assertTrue(all(row["availableCount"] > 0 for row in body["recommendations"]))


if __name__ == "__main__":
    unittest.main()
