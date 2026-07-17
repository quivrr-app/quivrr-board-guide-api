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

    @staticmethod
    def _compatible_inventory(rows, profile):
        updates = [
            {"selected_volume_litres": 24.0, "volume_delta_litres": 4.6, "volume_compatibility": "incompatible"},
            {"selected_volume_litres": 28.8, "volume_delta_litres": 0.2, "volume_compatibility": "excellent"},
            {"selected_volume_litres": 30.4, "volume_delta_litres": 1.8, "volume_compatibility": "good"},
            {"selected_volume_litres": 35.0, "volume_delta_litres": 6.4, "volume_compatibility": "incompatible"},
        ]
        seeded = []
        for index, row in enumerate(rows):
            extra = updates[index] if index < len(updates) else updates[1]
            seeded.append(row.model_copy(update={
                "available_count": 1,
                "retailer_count": 1,
                "region": profile.region or "ID",
                "region_code": profile.region or "ID",
                "selected_size_reason": "closest viable size for the rider",
                **extra,
            }))
        return seeded

    @staticmethod
    def _assert_categories_in_family(recommendations, allowed_categories):
        actual = {item["category"].lower() for item in recommendations}
        expected = {category.lower() for category in allowed_categories}
        assert actual, "expected at least one recommendation"
        unexpected = actual - expected
        assert not unexpected, f"unexpected categories: {sorted(unexpected)}"

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
        self.assertTrue(body["conversationState"]["authenticated"])
        self.assertEqual(body["conversationState"]["preferredName"], "Nathan")

    @patch("main.is_azure_openai_configured", return_value=False)
    @patch("main.enrich_suggestions_with_inventory", side_effect=lambda rows, _profile: rows)
    @patch("main.recommend_from_matrix")
    @patch("main.load_authenticated_profile_context")
    def test_authenticated_recommendation_waits_for_verified_profile(self, auth_loader, recommend_from_matrix, _inventory, _azure):
        auth_loader.return_value = AuthenticatedProfileContext(
            authenticated=True,
            profile_loaded=False,
            invalid_token=False,
            profile=None,
            status="loaded",
        )
        body = self.client.post(
            "/api/board-guide/chat",
            json={"message": "I need a good fish for Bali", "region": "ID"},
            headers={"Authorization": "Bearer token-123"},
        ).json()
        self.assertEqual(body["reply"], "Loading your saved rider profile...")
        self.assertTrue(body["authenticated"])
        self.assertFalse(body["profileLoaded"])
        self.assertEqual(body["recommendations"], [])
        self.assertEqual(body["missingQuestions"], [])
        recommend_from_matrix.assert_not_called()

    @patch("main.is_azure_openai_configured", return_value=False)
    @patch("main.enrich_suggestions_with_inventory", side_effect=lambda rows, _profile: rows)
    @patch("main.recommend_from_matrix")
    @patch("main.load_authenticated_profile_context")
    def test_authenticated_profile_failure_does_not_invent_intermediate(self, auth_loader, recommend_from_matrix, _inventory, _azure):
        auth_loader.return_value = AuthenticatedProfileContext(
            authenticated=True,
            profile_loaded=False,
            invalid_token=False,
            profile=None,
            status="failed",
        )
        body = self.client.post(
            "/api/board-guide/chat",
            json={"message": "I need a good fish for Bali", "region": "ID"},
            headers={"Authorization": "Bearer token-123"},
        ).json()
        self.assertIn("advanced level", body["reply"].lower())
        self.assertNotIn("intermediate", body["reply"].lower())
        self.assertEqual(body["recommendations"], [])
        recommend_from_matrix.assert_not_called()

    @patch("main.is_azure_openai_configured", return_value=False)
    @patch("main.enrich_suggestions_with_inventory", side_effect=_compatible_inventory)
    @patch("main.recommend_from_matrix")
    @patch("main.load_authenticated_profile_context")
    def test_authenticated_reef_fish_shortlist_uses_saved_advanced_profile_and_tight_target_volume(self, auth_loader, recommend_from_matrix, _inventory, _azure):
        recommend_from_matrix.return_value = self._seed_recommendations(4, "Performance Fish", region="ID")
        auth_loader.return_value = AuthenticatedProfileContext(
            authenticated=True,
            profile_loaded=True,
            user_id="user-123",
            profile=RiderProfile(
                display_name="Nathan Dunn",
                weight_kg=75,
                ability="Advanced",
                region="ID",
                wave_type="Reef Break",
                current_volume_litres=28.6,
                target_volume_litres=28.6,
                target_volume_source="saved_profile",
                target_volume_confidence="high",
                home_break="Canggu",
                goal="Performance progression",
                fieldProvenance={
                    "ability": "saved_profile",
                    "weight_kg": "saved_profile",
                    "current_volume_litres": "saved_profile",
                    "target_volume_litres": "saved_profile",
                    "region": "saved_profile",
                },
            ),
            status="loaded",
        )
        body = self.client.post(
            "/api/board-guide/chat",
            json={"message": "I need a good fish for Bali reefs.", "region": "ID"},
            headers={"Authorization": "Bearer token-123"},
        ).json()
        self.assertTrue(body["profileLoaded"])
        self.assertEqual(body["conversationProfile"]["ability"], "Advanced")
        self.assertEqual(body["profileAbilitySource"], "saved_profile")
        self.assertEqual(body["profileWeightSource"], "saved_profile")
        self.assertEqual(body["profileVolumeSource"], "saved_profile")
        self.assertEqual(body["targetVolume"]["targetLitres"], 28.6)
        self.assertEqual(body["targetVolume"]["minimumLitres"], 27.5)
        self.assertEqual(body["targetVolume"]["maximumLitres"], 30.5)
        self.assertIn("Using your saved 28.6L target", body["reply"])
        self.assertIn("performance fish and reef-capable twin designs", body["reply"])
        self.assertTrue(body["recommendations"])
        self.assertTrue(all(card["volumeCompatibility"] in {"excellent", "good"} for card in body["recommendations"]))
        selected_volumes = [card["selected_volume_litres"] for card in body["suggested_boards"] if card["selected_volume_litres"] is not None]
        self.assertTrue(selected_volumes)
        self.assertGreaterEqual(min(selected_volumes), 27.0)
        self.assertLessEqual(max(selected_volumes), 31.0)

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
        self.assertIn("You’re Nathan Dunn", body["reply"])
        self.assertIn("saved rider profile", body["reply"])
        self.assertTrue(body["profileLoaded"])

    @patch("main.is_azure_openai_configured", return_value=False)
    @patch("main.enrich_suggestions_with_inventory", side_effect=lambda rows, _profile: rows)
    def test_anonymous_whats_my_name_does_not_invent_identity(self, _inventory, _azure):
        body = self.client.post("/api/board-guide/chat", json={"message": "What's my name?"}).json()
        self.assertIn("while you’re signed out", body["reply"])
        self.assertFalse(body["profileLoaded"])

    @patch("main.is_azure_openai_configured", return_value=False)
    @patch("main.recommend_from_matrix")
    @patch("main.enrich_suggestions_with_inventory")
    def test_greetings_never_invoke_recommendations(self, inventory, recommend_from_matrix, _azure):
        for greeting in ["Hello", "Hi", "Hey", "Good morning", "Hey Bodhi", "Hey Bohdi", "Hey Bodi", "Hey mate", "Hello again"]:
            with self.subTest(greeting=greeting):
                body = self.client.post("/api/board-guide/chat", json={"message": greeting, "region": "AU"}).json()
                self.assertEqual(body["recommendations"], [])
                self.assertEqual(body["missingQuestions"], [])
                self.assertIsNone(body["volumeGuidance"])
                self.assertIsNone(body["category"])
        recommend_from_matrix.assert_not_called()
        inventory.assert_not_called()

    @patch("main.is_azure_openai_configured", return_value=False)
    @patch("main.recommend_from_matrix")
    @patch("main.enrich_suggestions_with_inventory")
    def test_general_help_never_invoke_recommendations(self, inventory, recommend_from_matrix, _azure):
        for message in ["Can you help me?", "What can you do?", "How are you?"]:
            with self.subTest(message=message):
                body = self.client.post("/api/board-guide/chat", json={"message": message, "region": "AU"}).json()
                self.assertEqual(body["recommendations"], [])
                self.assertIn(body["intent"], {"capability_help_request", "greeting_request"})
        recommend_from_matrix.assert_not_called()
        inventory.assert_not_called()

    @patch("main.recommend_from_matrix")
    @patch("main.enrich_suggestions_with_inventory")
    @patch("main.load_authenticated_profile_context")
    @patch("main.is_azure_openai_configured", return_value=False)
    def test_complete_profile_greeting_does_not_trigger_cards(self, _azure, auth_loader, inventory, recommend_from_matrix):
        auth_loader.return_value = AuthenticatedProfileContext(
            authenticated=True,
            profile_loaded=True,
            user_id="user-123",
            profile=RiderProfile(
                display_name="Nathan Dunn",
                ability="Advanced",
                region="ID",
                current_volume_litres=28.6,
                preferred_brands=["JS Industries", "Album"],
                home_break="Canggu",
                goal="Performance progression",
            ),
        )
        body = self.client.post("/api/board-guide/chat", json={"message": "Hey Bohdi"}, headers={"Authorization": "Bearer good"}).json()
        self.assertEqual(body["intent"], "greeting_request")
        self.assertEqual(body["recommendations"], [])
        self.assertIsNone(body["volumeGuidance"])
        self.assertTrue(body["reply"].startswith("Hey Nathan."))
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
        self.assertIn("30.5 to 34L", first["reply"])
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
    def test_broad_request_returns_three_role_based_public_cards(self, inventory, recommend_from_matrix, _azure):
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
        self.assertEqual(len(body["recommendations"]), 3)
        self.assertEqual(
            [card["selectionRole"] for card in body["recommendations"]],
            ["Best overall fit", "More forgiving direction", "More performance-oriented direction"],
        )
        self.assertTrue(all(card["selectionRationale"] for card in body["recommendations"]))

    @patch("main.is_azure_openai_configured", return_value=False)
    @patch("main.recommend_from_matrix")
    @patch("main.enrich_suggestions_with_inventory")
    def test_broad_hybrid_and_performance_requests_return_three_diverse_cards(self, inventory, recommend_from_matrix, _azure):
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
                self.assertEqual(len(body["recommendations"]), 3)
                self.assertGreaterEqual(len({card["brand"] for card in body["recommendations"]}), 2)

    @patch("main.is_azure_openai_configured", return_value=False)
    @patch("main.recommend_from_matrix")
    @patch("main.enrich_suggestions_with_inventory")
    def test_volume_and_region_fish_request_without_weight_can_still_return_cards(self, inventory, recommend_from_matrix, _azure):
        seeded = self._seed_recommendations(6, "Fish", region="ID")
        recommend_from_matrix.return_value = seeded
        inventory.side_effect = lambda rows, profile: [
            row.model_copy(update={
                "available_count": 1 if index == 0 else 0,
                "retailer_count": 1 if index == 0 else 0,
                "region": "ID",
                "region_code": "ID",
            })
            for index, row in enumerate(rows)
        ]
        body = self.client.post("/api/board-guide/chat", json={
            "message": "I want a fish for small weak waves around 29L in Indonesia",
            "region": "ID",
        }).json()
        self.assertGreaterEqual(len(body["recommendations"]), 3)
        self.assertNotIn("I still need your weight", body["reply"])
        self.assertTrue(any(card["availableCount"] == 0 for card in body["recommendations"]))

    @patch("main.recommend_from_matrix")
    @patch("main.enrich_suggestions_with_inventory")
    @patch("main.is_azure_openai_configured", return_value=False)
    def test_ambiguous_new_board_request_asks_question_instead_of_guessing(self, _azure, inventory, recommend_from_matrix):
        body = self.client.post("/api/board-guide/chat", json={
            "message": "I want a new board",
            "profile": {"weight_kg": 78, "ability": "Advanced", "region": "ID", "wave_type": "Reef Break"},
        }).json()
        self.assertEqual(body["recommendations"], [])
        self.assertTrue(body["missingQuestions"])
        self.assertIn("What kind of board", body["reply"])
        recommend_from_matrix.assert_not_called()
        inventory.assert_not_called()

    @patch("main.is_azure_openai_configured", return_value=False)
    @patch("main.enrich_suggestions_with_inventory", side_effect=lambda rows, _profile: rows)
    def test_performance_shortboard_shortlist_stays_in_family(self, _inventory, _azure):
        body = self.client.post("/api/board-guide/chat", json={
            "message": "Show me six performance shortboards",
            "profile": {"weight_kg": 75, "ability": "Advanced", "region": "AU", "wave_type": "Point Break", "wave_power": "Average to Powerful"},
            "region": "AU",
        }).json()
        self.assertGreaterEqual(len(body["recommendations"]), 3)
        self._assert_categories_in_family(
            body["recommendations"],
            {"High Performance Shortboard", "Performance Shortboard", "Performance Daily Driver", "Competition Shortboard"},
        )
        self.assertEqual(body["category"], "performance_shortboard")
        self.assertEqual(body["categorySource"], "explicit_user_request")
        self.assertGreater(body["categoryConfidence"], 0.9)

    @patch("main.is_azure_openai_configured", return_value=False)
    @patch("main.enrich_suggestions_with_inventory", side_effect=lambda rows, _profile: rows)
    def test_strict_hpsb_request_excludes_ghost_xl_and_bom_dia(self, _inventory, _azure):
        body = self.client.post("/api/board-guide/chat", json={
            "message": "I want a true performance shortboard for stronger waves",
            "profile": {
                "age": 45,
                "weight_kg": 75,
                "ability": "Advanced",
                "current_volume_litres": 28.6,
                "target_volume_litres": 28.6,
                "region": "ID",
                "fitness": "Good",
                "surf_frequency": 3,
                "paddle_strength": "Good",
                "preferred_board_type": "True performance shortboard",
                "goal": "Performance progression",
                "wave_power": "Powerful",
            },
            "region": "ID",
        }).json()
        names = {(card["brand"], card["model"]) for card in body["recommendations"]}
        self.assertIn(("JS Industries", "Monsta"), names)
        self.assertNotIn(("Pyzel", "Ghost XL"), names)
        self.assertNotIn(("Album", "Bom Dia"), names)

    @patch("main.is_azure_openai_configured", return_value=False)
    @patch("main.enrich_suggestions_with_inventory", side_effect=lambda rows, _profile: rows)
    def test_performance_twin_request_uses_twin_family(self, _inventory, _azure):
        body = self.client.post("/api/board-guide/chat", json={
            "message": "Show me performance twins instead",
            "profile": {
                "age": 45,
                "weight_kg": 75,
                "ability": "Advanced",
                "current_volume_litres": 28.6,
                "target_volume_litres": 28.6,
                "region": "ID",
                "fitness": "Good",
                "surf_frequency": 3,
                "paddle_strength": "Good",
                "preferred_board_type": "True performance shortboard",
                "goal": "Performance progression",
                "wave_power": "Powerful",
            },
            "region": "ID",
        }).json()
        self.assertGreaterEqual(len(body["recommendations"]), 1)
        self.assertTrue(any(card["model"] == "Bom Dia" for card in body["recommendations"]))
        self._assert_categories_in_family(body["recommendations"], {"Performance Twin"})

    @patch("main.is_azure_openai_configured", return_value=False)
    @patch("main.enrich_suggestions_with_inventory", side_effect=lambda rows, _profile: rows)
    def test_fish_shortlist_stays_in_family(self, _inventory, _azure):
        body = self.client.post("/api/board-guide/chat", json={
            "message": "Show me six fish boards",
            "profile": {"weight_kg": 75, "ability": "Intermediate", "region": "AU", "wave_type": "Beach Break", "wave_power": "Weak"},
            "region": "AU",
        }).json()
        self.assertGreaterEqual(len(body["recommendations"]), 3)
        self._assert_categories_in_family(
            body["recommendations"],
            {"Fish", "Performance Fish", "Cruisy Fish", "Modern Fish", "Traditional Fish", "Small Wave Fish"},
        )
        self.assertEqual(body["category"], "fish")

    @patch("main.is_azure_openai_configured", return_value=False)
    @patch("main.enrich_suggestions_with_inventory", side_effect=lambda rows, _profile: rows)
    def test_small_wave_shortlist_stays_in_family(self, _inventory, _azure):
        body = self.client.post("/api/board-guide/chat", json={
            "message": "I want a small-wave board",
            "profile": {"weight_kg": 75, "ability": "Intermediate", "region": "AU", "wave_type": "Beach Break", "wave_power": "Weak"},
            "region": "AU",
        }).json()
        self.assertGreaterEqual(len(body["recommendations"]), 3)
        self._assert_categories_in_family(
            body["recommendations"],
            {"Groveller", "Small Wave Shortboard", "Fish", "Performance Fish", "Hybrid Shortboard", "Performance Daily Driver"},
        )
        self.assertEqual(body["category"], "small_wave")

    @patch("main.is_azure_openai_configured", return_value=False)
    @patch("main.enrich_suggestions_with_inventory", side_effect=lambda rows, _profile: rows)
    def test_step_up_shortlist_stays_in_family(self, _inventory, _azure):
        body = self.client.post("/api/board-guide/chat", json={
            "message": "I need a step up for Bali",
            "profile": {"weight_kg": 75, "ability": "Advanced", "region": "ID", "wave_type": "Reef Break", "wave_power": "Powerful"},
            "region": "ID",
        }).json()
        self.assertGreaterEqual(len(body["recommendations"]), 1)
        self._assert_categories_in_family(
            body["recommendations"],
            {"Step Up", "Powerful Wave Board", "Semi Gun", "Travel Step Up"},
        )
        self.assertEqual(body["category"], "step_up")

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
    @patch("main.recommend_from_matrix")
    @patch("main.enrich_suggestions_with_inventory")
    def test_explicit_stock_only_request_returns_only_verified_available_cards(self, inventory, recommend_from_matrix, _azure):
        recommend_from_matrix.return_value = self._seed_recommendations(4, "Performance Shortboard", region="ID")
        inventory.side_effect = lambda rows, profile: [
            row.model_copy(update={
                "available_count": 1 if index == 0 else 0,
                "manufacturer_direct_count": 1 if index == 0 else 0,
                "retailer_count": 0,
                "availability_checked": True,
                "availability_status": "available" if index == 0 else "not_found",
                "region": profile.region or "ID",
                "region_code": profile.region or "ID",
            })
            for index, row in enumerate(rows)
        ]
        body = self.client.post("/api/board-guide/chat", json={
            "message": "I need a new short board, just show me ones in stock in indo",
            "profile": {"weight_kg": 75, "ability": "Advanced", "region": "ID", "wave_type": "Reef Break", "wave_power": "Average to Powerful"},
            "region": "ID",
        }).json()
        self.assertEqual(len(body["recommendations"]), 1)
        self.assertTrue(all(card["availableCount"] > 0 for card in body["recommendations"]))
        self.assertEqual(body["conversationState"]["availabilityConstraint"], "VERIFIED_IN_STOCK")
        self.assertIn("one suitable", body["reply"].lower())

    @patch("main.is_azure_openai_configured", return_value=False)
    @patch("main.recommend_from_matrix")
    @patch("main.enrich_suggestions_with_inventory")
    def test_available_in_my_size_means_verified_stock_and_narrative_matches_cards(self, inventory, recommend_from_matrix, _azure):
        recommend_from_matrix.return_value = self._seed_recommendations(4, "Performance Fish", region="ID")
        inventory.side_effect = lambda rows, profile: [
            row.model_copy(update={
                "available_count": 1 if index < 2 else 0,
                "manufacturer_direct_count": 1 if index == 0 else 0,
                "retailer_count": 1 if index == 1 else 0,
                "availability_checked": True,
                "availability_status": "manufacturer_stock" if index == 0 else "retailer_stock" if index == 1 else "not_found",
                "exact_size_inventory_count": 1 if index < 2 else 0,
                "exact_size_stock": index < 2,
                "model_level_stock": index < 2,
                "selected_volume_litres": 28.5 + index,
                "volume_compatibility": "excellent" if index == 0 else "good",
                "region": profile.region or "ID",
                "region_code": profile.region or "ID",
            })
            for index, row in enumerate(rows)
        ]
        body = self.client.post("/api/board-guide/chat", json={
            "message": "What's available in my size in Indonesia? I want a fish for the reef breaks here.",
            "profile": {"weight_kg": 75, "ability": "Advanced", "target_volume_litres": 28.6, "region": "ID", "wave_type": "Reef Break"},
            "region": "ID",
        }).json()
        self.assertEqual(body["conversationState"]["availabilityConstraint"], "VERIFIED_IN_STOCK")
        self.assertEqual(len(body["recommendations"]), 2)
        self.assertIn("I found 2", body["reply"])
        self.assertTrue(all(card["availableCount"] > 0 for card in body["recommendations"]))
        self.assertTrue(all(card["availabilityStatus"] in {"manufacturer_stock", "retailer_stock"} for card in body["recommendations"]))
        self.assertNotIn("Catalogue model", body["reply"])

    @patch("main.is_azure_openai_configured", return_value=False)
    @patch("main.enrich_suggestions_with_inventory")
    def test_corrective_stock_follow_up_filters_previous_cards_instead_of_repeating_them(self, inventory, _azure):
        inventory.side_effect = lambda rows, profile: [
            row.model_copy(update={
                "available_count": 1 if row.brand == "Album" else 0,
                "retailer_count": 1 if row.brand == "Album" else 0,
                "availability_checked": True,
                "availability_status": "retailer_stock" if row.brand == "Album" else "not_found",
                "model_level_stock": row.brand == "Album",
                "region": profile.region or "ID",
                "region_code": profile.region or "ID",
            }) for row in rows
        ]
        body = self.client.post("/api/board-guide/chat", json={
            "message": "I asked for you to show me boards in stock",
            "region": "ID",
            "conversationState": {
                "activeRegion": "ID",
                "lastRecommendations": [
                    self._state_card("Album", "Lightbender", "Performance Fish", "Reef-capable fish."),
                    self._state_card("Firewire", "Seaside", "Fish", "Fast traditional fish."),
                ],
                "conversationTurn": 2,
            },
            "intakeState": {"weight_kg": 75, "ability": "Advanced", "target_volume_litres": 28.6, "region": "ID", "preferred_board_type": "Fish", "wave_type": "Reef Break"},
        }).json()
        self.assertEqual(body["conversationState"]["availabilityConstraint"], "VERIFIED_IN_STOCK")
        self.assertTrue(body["recommendations"])
        self.assertTrue(all(card["brand"] == "Album" for card in body["recommendations"]))
        self.assertNotIn("Seaside", body["reply"])

    @patch("main.is_azure_openai_configured", return_value=False)
    @patch("main.enrich_suggestions_with_inventory")
    def test_stock_only_follow_up_is_preserved_for_new_category(self, inventory, _azure):
        inventory.side_effect = lambda rows, profile: [
            row.model_copy(update={
                "available_count": 1 if index < 2 else 0,
                "manufacturer_direct_count": 1 if index < 2 else 0,
                "retailer_count": 0,
                "availability_checked": True,
                "availability_status": "available" if index < 2 else "not_found",
                "region": profile.region or "EU",
                "region_code": profile.region or "EU",
            })
            for index, row in enumerate(rows)
        ]
        body = self.client.post("/api/board-guide/chat", json={
            "message": "Show me fish instead",
            "region": "EU",
            "conversationState": {
                "activeRegion": "EU",
                "availabilityConstraint": "VERIFIED_IN_STOCK",
                "conversationTurn": 2,
            },
            "intakeState": {
                "weight_kg": 75,
                "ability": "Intermediate",
                "region": "EU",
            },
        }).json()
        self.assertEqual(body["category"], "fish")
        self.assertEqual(body["conversationState"]["availabilityConstraint"], "VERIFIED_IN_STOCK")
        self.assertTrue(all(card["availableCount"] > 0 for card in body["recommendations"]))

    @patch("main.is_azure_openai_configured", return_value=False)
    @patch("main.recommend_from_matrix")
    @patch("main.enrich_suggestions_with_inventory")
    def test_stock_only_constraint_can_be_removed_explicitly(self, inventory, recommend_from_matrix, _azure):
        recommend_from_matrix.return_value = self._seed_recommendations(3, "Fish", region="ID")
        inventory.side_effect = lambda rows, profile: [
            row.model_copy(update={
                "available_count": 1 if index == 0 else 0,
                "manufacturer_direct_count": 1 if index == 0 else 0,
                "retailer_count": 0,
                "availability_checked": True,
                "availability_status": "available" if index == 0 else "not_found",
                "region": profile.region or "ID",
                "region_code": profile.region or "ID",
            })
            for index, row in enumerate(rows)
        ]
        body = self.client.post("/api/board-guide/chat", json={
            "message": "Show catalogue options too",
            "region": "ID",
            "conversationState": {
                "activeRegion": "ID",
                "availabilityConstraint": "VERIFIED_IN_STOCK",
                "conversationTurn": 3,
            },
            "intakeState": {
                "weight_kg": 75,
                "ability": "Intermediate",
                "region": "ID",
                "preferred_board_type": "Fish",
            },
        }).json()
        self.assertIsNone(body["conversationState"]["availabilityConstraint"])
        self.assertGreaterEqual(len(body["recommendations"]), 1)
        self.assertTrue(any(card["availableCount"] == 0 for card in body["recommendations"]))

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

    @patch("main.is_azure_openai_configured", return_value=False)
    def test_compact_frontend_conversation_state_cards_are_accepted(self, _azure):
        compact_state = {
            "lastIntent": "BOARD_RECOMMENDATION",
            "activeRegion": "ID",
            "lastRecommendations": [
                {
                    "brand": "JS Industries",
                    "model": "Black Baron",
                    "category": "Performance Fish",
                    "shortReason": "Fast fish with good bite.",
                    "fitScore": 94,
                    "regionCode": "ID",
                    "searchUrl": "https://quivrr.app/indonesia/?brand=JS+Industries&model=Black+Baron",
                },
                {
                    "brand": "Firewire",
                    "model": "Seaside",
                    "category": "Cruisy Fish",
                    "shortReason": "Easy speed and flow.",
                    "fitScore": 94,
                    "regionCode": "ID",
                    "searchUrl": "https://quivrr.app/indonesia/?brand=Firewire&model=Seaside",
                },
                {
                    "brand": "Lost",
                    "model": "RNF 96",
                    "category": "Modern Fish",
                    "shortReason": "More performance-led fish.",
                    "fitScore": 94,
                    "regionCode": "ID",
                    "searchUrl": "https://quivrr.app/indonesia/?brand=Lost&model=RNF+96",
                },
                {
                    "brand": "Chemistry Surfboards",
                    "model": "Holiday",
                    "category": "Fish",
                    "shortReason": "Broader catalogue option.",
                    "fitScore": 78,
                    "regionCode": "ID",
                    "searchUrl": "https://quivrr.app/indonesia/?brand=Chemistry+Surfboards&model=Holiday",
                },
            ],
            "comparisonBoards": [],
            "conversationTurn": 3,
        }
        response = self.client.post("/api/board-guide/chat", json={
            "message": "Tell me about number 3.",
            "conversationState": compact_state,
            "region": "ID",
        })
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("Lost RNF 96", body["reply"])


if __name__ == "__main__":
    unittest.main()
