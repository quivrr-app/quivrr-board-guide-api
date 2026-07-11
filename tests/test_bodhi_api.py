import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import main
from app.authenticated_profile import AuthenticatedProfileContext
from app.models import RiderProfile, SuggestedBoard


class BodhiApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)

    @staticmethod
    def _seed_recommendations(count: int, category: str, region: str = "AU"):
        return [
            SuggestedBoard(
                brand=f"Brand {index // 2}",
                model=f"Model {index}",
                category=category,
                confidence=0.9,
                why_it_fits=f"{category} fit {index}",
                fit_score=90 - index,
                region=region,
                region_code=region,
            )
            for index in range(count)
        ]

    @staticmethod
    def _state_card(brand: str, model: str, category: str, short_reason: str, region: str = "ID"):
        return {
            "brand": brand,
            "model": model,
            "category": category,
            "shortReason": short_reason,
            "whyItFits": short_reason,
            "sourceType": "retailer",
            "confidence": 0.9,
            "region": region,
            "regionCode": region,
        }

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
    @patch("main.load_authenticated_profile_context")
    def test_whats_my_name_uses_verified_profile_only(self, auth_loader, _inventory, _azure):
        auth_loader.return_value = AuthenticatedProfileContext(
            authenticated=True,
            profile_loaded=True,
            user_id="user-123",
            profile=RiderProfile(display_name="Nathan Dunn", region="ID"),
        )
        response = self.client.post(
            "/api/board-guide/chat",
            json={"message": "What's my name?"},
            headers={"Authorization": "Bearer token-123"},
        )
        body = response.json()
        self.assertEqual(body["reply"], "You're Nathan Dunn.")
        self.assertTrue(body["profileLoaded"])

    @patch("main.is_azure_openai_configured", return_value=False)
    @patch("main.enrich_suggestions_with_inventory", side_effect=lambda rows, _profile: rows)
    def test_anonymous_whats_my_name_does_not_invent_identity(self, _inventory, _azure):
        body = self.client.post("/api/board-guide/chat", json={"message": "What's my name?"}).json()
        self.assertIn("verified saved identity", body["reply"])
        self.assertFalse(body["profileLoaded"])

    @patch("main.is_azure_openai_configured", return_value=False)
    @patch("main.recommend_from_matrix")
    @patch("main.enrich_suggestions_with_inventory")
    def test_greetings_never_invoke_recommendations(self, inventory, recommend_from_matrix, _azure):
        for greeting in ["Hello", "Hi", "Hey", "Good morning"]:
            with self.subTest(greeting=greeting):
                body = self.client.post("/api/board-guide/chat", json={"message": greeting, "region": "AU"}).json()
                self.assertEqual(body["recommendations"], [])
                self.assertEqual(body["missingQuestions"], [])
        recommend_from_matrix.assert_not_called()
        inventory.assert_not_called()

    @patch("main.is_azure_openai_configured", return_value=False)
    @patch("main.recommend_from_matrix")
    @patch("main.enrich_suggestions_with_inventory")
    def test_general_help_never_invoke_recommendations(self, inventory, recommend_from_matrix, _azure):
        for message in ["Can you help me?", "What can you do?"]:
            with self.subTest(message=message):
                body = self.client.post("/api/board-guide/chat", json={"message": message, "region": "AU"}).json()
                self.assertEqual(body["recommendations"], [])
                self.assertEqual(body["intent"], "capability_help_request")
                self.assertIn("choose a board", body["reply"])
        recommend_from_matrix.assert_not_called()
        inventory.assert_not_called()

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
    @patch("main.locate_exact_board", return_value=([], False))
    @patch("main.enrich_suggestions_with_inventory", side_effect=_alternatives_inventory)
    def test_out_of_stock_uses_live_graph_alternative(self, _inventory, _locate, _azure):
        response = self.client.post("/api/board-guide/chat", json={
            "message": "Is the JS Xero Gravity available?", "region": "AU",
        })
        body = response.json()
        self.assertEqual(body["recommendations"], [])
        self.assertIn("haven’t invented a substitute link", body["reply"])

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
        self.assertTrue(any(row["availableCount"] > 0 for row in third["recommendations"]))

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
        self.assertIn("verified AU stock", body["reply"])
        self.assertTrue(any(row["availableCount"] == 0 for row in body["recommendations"]))

    @patch("main.is_azure_openai_configured", return_value=False)
    @patch("main.recommend_from_matrix")
    @patch("main.enrich_suggestions_with_inventory")
    def test_broad_request_caps_public_cards_at_six(self, inventory, recommend_from_matrix, _azure):
        seeded = self._seed_recommendations(8, "Fish")
        recommend_from_matrix.return_value = seeded
        inventory.side_effect = lambda rows, profile: [
            row.model_copy(update={"available_count": 1, "retailer_count": 1, "region": profile.region or "AU", "region_code": profile.region or "AU"})
            for row in rows
        ]
        body = self.client.post("/api/board-guide/chat", json={
            "message": "I need a fish for weak waves",
            "profile": {"weight_kg": 75, "ability": "Intermediate", "region": "AU", "wave_type": "Beach Break", "wave_power": "Weak"},
        }).json()
        self.assertEqual(len(body["recommendations"]), 6)
        self.assertLessEqual(len(body["recommendations"]), 6)

    @patch("main.is_azure_openai_configured", return_value=False)
    @patch("main.recommend_from_matrix")
    @patch("main.enrich_suggestions_with_inventory")
    def test_broad_hybrid_and_performance_requests_normally_return_six(self, inventory, recommend_from_matrix, _azure):
        recommend_from_matrix.side_effect = [
            self._seed_recommendations(8, "Hybrid"),
            self._seed_recommendations(8, "Performance shortboard"),
        ]
        inventory.side_effect = lambda rows, profile: [
            row.model_copy(update={"available_count": 1, "retailer_count": 1, "region": profile.region or "AU", "region_code": profile.region or "AU"})
            for row in rows
        ]
        cases = [
            "I'm 75kg intermediate surfing 2-4ft beach breaks in Australia and want a hybrid.",
            "I'm 75kg intermediate surfing 3-5ft point breaks in Australia and want a performance shortboard.",
        ]
        for message in cases:
            with self.subTest(message=message):
                body = self.client.post("/api/board-guide/chat", json={"message": message, "region": "AU"}).json()
                self.assertEqual(len(body["recommendations"]), 6)
                self.assertGreaterEqual(len({card["brand"] for card in body["recommendations"]}), 3)

    @patch("main.is_azure_openai_configured", return_value=False)
    @patch("main.enrich_suggestions_with_inventory")
    def test_follow_up_filters_to_verified_regional_stock_and_remove_brand(self, inventory, _azure):
        inventory.side_effect = lambda rows, profile: [
            row.model_copy(update={
                "available_count": 1 if row.brand == "Album" else 0,
                "retailer_count": 1 if row.brand == "Album" else 0,
                "region": profile.region or "ID",
                "region_code": profile.region or "ID",
            })
            for row in rows
        ]
        state = {
            "lastRecommendations": [
                self._state_card("Pyzel", "Phantom", "Daily driver", "Balanced performance."),
                self._state_card("Album", "Bom Dia", "Twin pin", "Point-break trim."),
            ],
            "comparisonBoards": [],
            "conversationTurn": 2,
        }
        filtered = self.client.post("/api/board-guide/chat", json={
            "message": "Only show boards available in Indonesia",
            "conversationState": state,
            "region": "ID",
        }).json()
        self.assertEqual(len(filtered["recommendations"]), 1)
        self.assertEqual(filtered["recommendations"][0]["brand"], "Album")
        self.assertIn("verified current availability in Indonesia", filtered["reply"])

        removed = self.client.post("/api/board-guide/chat", json={
            "message": "Remove Pyzel",
            "conversationState": state,
            "region": "ID",
        }).json()
        self.assertTrue(all(board["brand"] != "Pyzel" for board in removed["recommendations"]))

    @patch("main.is_azure_openai_configured", return_value=False)
    @patch("main.enrich_suggestions_with_inventory", side_effect=lambda rows, profile: [
        row.model_copy(update={"available_count": 1, "retailer_count": 1, "region": profile.region or "ID", "region_code": profile.region or "ID"})
        for row in rows
    ])
    def test_numbered_follow_up_uses_conversation_state(self, _inventory, _azure):
        state = {
            "lastRecommendations": [
                self._state_card("JS Industries", "Monsta", "Performance shortboard", "Sharp and fast."),
                self._state_card("Pyzel", "Ghost", "Step up", "Holds when the surf gets heavier."),
                self._state_card("Album", "Bom Dia", "Twin pin", "Clean point-break lines."),
                self._state_card("Pyzel", "Phantom", "Daily driver", "Balanced performance."),
            ],
            "comparisonBoards": [],
            "conversationTurn": 3,
        }
        detail = self.client.post("/api/board-guide/chat", json={
            "message": "Tell me about number 3",
            "conversationState": state,
            "region": "ID",
        }).json()
        self.assertIn("Album Bom Dia", detail["reply"])
        self.assertEqual(detail["recommendations"], [])

        compare = self.client.post("/api/board-guide/chat", json={
            "message": "Compare number 1 and number 4",
            "conversationState": state,
            "region": "ID",
        }).json()
        self.assertIn("Paddle power:", compare["reply"])
        self.assertIsNotNone(compare["comparison"])
        self.assertEqual(len(compare["conversationState"]["comparisonBoards"]), 2)


if __name__ == "__main__":
    unittest.main()
