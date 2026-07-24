import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import main
from app.authenticated_profile import AuthenticatedProfileContext
from app.models import RiderProfile


class AuthTransitionRoutingTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)
        self.saved = AuthenticatedProfileContext(
            authenticated=True,
            profile_loaded=True,
            user_id="nathan-1",
            status="loaded",
            profile=RiderProfile(
                display_name="Nathan Dunn", weight_kg=74, ability="Advanced",
                current_volume_litres=28.6, region="AU",
            ),
        )

    def _assert_no_recommendation(self, body):
        self.assertEqual(body["recommendations"], [])
        self.assertEqual(body["suggested_boards"], [])
        self.assertIsNone(body["recommendation"])
        self.assertEqual(body["followUpActions"], [])

    def test_signed_out_identity_query_cannot_verify_name(self):
        body = self.client.post("/api/board-guide/chat", json={"message": "what's my name", "region": "AU"}).json()
        self.assertIn("can’t verify your name while you’re signed out", body["reply"])
        self.assertEqual(body["normalizedIntent"], "IDENTITY_QUERY")
        self._assert_no_recommendation(body)

    @patch("main.load_authenticated_profile_context")
    @patch("main.recommend_from_matrix")
    def test_signed_in_acknowledgement_refreshes_identity_without_recommendation(self, recommend, profile_context):
        profile_context.return_value = self.saved
        body = self.client.post("/api/board-guide/chat", headers={"Authorization": "Bearer test"}, json={
            "message": "ok i just signed in", "region": "AU", "conversationState": {},
        }).json()
        self.assertEqual(body["normalizedIntent"], "AUTH_STATE_UPDATE")
        self.assertIn("signed in as Nathan Dunn", body["reply"])
        self.assertEqual(body["responseMode"], "conversation_only")
        self._assert_no_recommendation(body)
        recommend.assert_not_called()

    @patch("main.load_authenticated_profile_context")
    @patch("main.recommend_from_matrix")
    def test_correction_clears_stale_plan_without_recommendation(self, recommend, profile_context):
        profile_context.return_value = self.saved
        body = self.client.post("/api/board-guide/chat", headers={"Authorization": "Bearer test"}, json={
            "message": "I didn't ask for anything", "region": "AU",
            "conversationState": {
                "lastIntent": "BOARD_RECOMMENDATION",
                "lastRecommendations": [{"brand": "Sharp Eye", "model": "Inferno 72", "category": "Performance Daily Driver", "confidence": 0.9}],
            },
        }).json()
        self.assertEqual(body["normalizedIntent"], "NO_REQUEST")
        self.assertIn("misread", body["reply"])
        self.assertTrue(body["conversationState"]["correctionDetected"])
        self.assertEqual(body["conversationState"]["lastRecommendations"], [])
        self._assert_no_recommendation(body)
        recommend.assert_not_called()

    @patch("main.emit_event")
    @patch("main.load_authenticated_profile_context")
    @patch("main.recommend_from_matrix")
    def test_correction_emits_complete_transition_routing_fields(self, recommend, profile_context, emit_event):
        profile_context.return_value = self.saved
        self.client.post("/api/board-guide/chat", headers={"Authorization": "Bearer test"}, json={
            "message": "I didn't ask for anything", "region": "AU",
            "conversationState": {
                "lastIntent": "BOARD_RECOMMENDATION",
                "lastRecommendations": [{"brand": "Sharp Eye", "model": "Inferno 72", "category": "Performance Daily Driver"}],
            },
        })
        routing = next(call.kwargs for call in emit_event.call_args_list if call.args[0] == "bodhi_turn_routing")
        self.assertEqual(routing["raw_current_message"], "I didn't ask for anything")
        self.assertFalse(routing["authenticated_before_refresh"])
        self.assertTrue(routing["bearer_present_before_hydration"])
        self.assertTrue(routing["auth_state_after_hydration"])
        self.assertEqual(routing["previous_intent"], "BOARD_RECOMMENDATION")
        self.assertEqual(routing["current_classified_intent"], "NO_REQUEST")
        self.assertEqual(routing["resolved_intent"], "NO_REQUEST")
        self.assertTrue(routing["correction_detected"])
        self.assertFalse(routing["recommendation_engine_invoked"])
        self.assertFalse(routing["previous_response_plan_reused"])
        self.assertEqual(routing["saved_profile_hydration_event"], "loaded")
        self.assertEqual(routing["active_conversation_state"]["lastIntent"], "BOARD_RECOMMENDATION")
        self.assertEqual(routing["response_mode"], "conversation_only")
        recommend.assert_not_called()

    @patch("main.load_authenticated_profile_context")
    @patch("main.recommend_from_matrix")
    def test_auth_refresh_event_without_chat_text_only_hydrates_context(self, recommend, profile_context):
        profile_context.return_value = self.saved
        body = self.client.post("/api/board-guide/chat", headers={"Authorization": "Bearer test"}, json={
            "message": "", "eventType": "AUTH_STATE_UPDATE", "region": "AU",
        }).json()
        self.assertEqual(body["normalizedIntent"], "AUTH_STATE_UPDATE")
        self.assertIn("signed in as Nathan Dunn", body["reply"])
        self._assert_no_recommendation(body)
        recommend.assert_not_called()

    @patch("main.recommend_from_matrix")
    def test_unverified_auth_update_never_claims_that_the_user_is_signed_in(self, recommend):
        body = self.client.post("/api/board-guide/chat", json={
            "message": "ok i just signed in", "region": "AU",
        }).json()
        self.assertEqual(body["normalizedIntent"], "AUTH_STATE_UPDATE")
        self.assertIn("can’t see a verified signed-in session", body["reply"])
        self._assert_no_recommendation(body)
        recommend.assert_not_called()

    @patch("main.recommend_from_matrix")
    def test_empty_message_never_falls_back_to_recommendation(self, recommend):
        body = self.client.post("/api/board-guide/chat", json={"message": "", "region": "AU"}).json()
        self.assertEqual(body["normalizedIntent"], "NO_REQUEST")
        self._assert_no_recommendation(body)
        recommend.assert_not_called()

    @patch("main.recommend_from_matrix")
    def test_acknowledgements_do_not_recommend_without_confirmation(self, recommend):
        for message in ("ok", "thanks", "got it"):
            with self.subTest(message=message):
                body = self.client.post("/api/board-guide/chat", json={"message": message, "region": "AU"}).json()
                self.assertEqual(body["normalizedIntent"], "ACKNOWLEDGEMENT_ONLY")
                self._assert_no_recommendation(body)
        recommend.assert_not_called()

    @patch("main.load_authenticated_profile_context")
    @patch("main.enrich_suggestions_with_inventory", side_effect=lambda boards, *_args, **_kwargs: boards)
    def test_explicit_board_request_still_invokes_recommendation_engine(self, _inventory, profile_context):
        profile_context.return_value = self.saved
        body = self.client.post("/api/board-guide/chat", headers={"Authorization": "Bearer test"}, json={
            "message": "I am advanced, 78 kg, and want a performance daily driver for average 3 to 5 foot waves.", "region": "AU",
        }).json()
        self.assertEqual(body["normalizedIntent"], "BOARD_RECOMMENDATION")
        self.assertNotEqual(body["responseMode"], "conversation_only")
        self.assertGreater(len(body["recommendations"]), 0)


if __name__ == "__main__":
    unittest.main()
