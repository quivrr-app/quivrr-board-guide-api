import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import main
from app.conversation_orchestration import TOOL_NAMES
from app.authenticated_profile import AuthenticatedProfileContext
from app.models import RiderProfile


class ConversationOrchestrationTests(unittest.TestCase):
    def test_governed_tool_contract_is_explicit(self):
        self.assertEqual(TOOL_NAMES, {
            "resolve_board", "recommend_boards", "check_model_availability", "compare_boards",
            "get_regional_inventory_summary", "get_platform_catalogue_facts", "read_authenticated_profile",
            "propose_profile_update", "confirm_profile_update", "reject_profile_update",
            "generate_exact_search_handoff",
        })

    def setUp(self):
        self.client = TestClient(main.app)
        self.saved = AuthenticatedProfileContext(
            authenticated=True,
            profile_loaded=True,
            user_id="nathan-1",
            status="loaded",
            profile=RiderProfile(display_name="Nathan Dunn", weight_kg=70, ability="Advanced", region="AU"),
        )

    def _assert_no_recommendations(self, body):
        self.assertEqual(body["recommendations"], [])
        self.assertEqual(body["suggested_boards"], [])
        self.assertIsNone(body["recommendation"])
        self.assertEqual(body["followUpActions"], [])

    @patch("main.load_authenticated_profile_context")
    @patch("main.recommend_from_matrix")
    def test_profile_acknowledgement_keeps_pending_proposal_without_recommendation(self, recommend, profile_context):
        profile_context.return_value = self.saved
        headers = {"Authorization": "Bearer test"}
        proposal = self.client.post("/api/board-guide/chat", headers=headers, json={
            "message": "Update my profile. I'm 75 kg.", "region": "AU",
        }).json()
        self.assertIsNotNone(proposal["profileUpdateProposal"])
        self.assertEqual(proposal["conversationState"]["pendingAction"]["type"], "profile_update")
        acknowledgement = self.client.post("/api/board-guide/chat", headers=headers, json={
            "message": "Great, thanks for that.", "region": "AU",
            "conversationState": proposal["conversationState"],
        }).json()
        self.assertEqual(acknowledgement["responseMode"], "conversation")
        self.assertIn("keep that profile update ready", acknowledgement["reply"])
        self.assertEqual(acknowledgement["conversationState"]["pendingAction"]["type"], "profile_update")
        self._assert_no_recommendations(acknowledgement)
        recommend.assert_not_called()

    @patch("main.load_authenticated_profile_context")
    @patch("main.recommend_from_matrix")
    def test_explicit_confirmation_only_confirms_pending_profile_action(self, recommend, profile_context):
        profile_context.return_value = self.saved
        headers = {"Authorization": "Bearer test"}
        proposal = self.client.post("/api/board-guide/chat", headers=headers, json={
            "message": "Update my profile. I'm 75 kg.", "region": "AU",
        }).json()
        confirmation = self.client.post("/api/board-guide/chat", headers=headers, json={
            "message": "Yes, update it.", "region": "AU",
            "conversationState": proposal["conversationState"],
        }).json()
        self.assertTrue(confirmation["profileUpdateConfirmationRequested"])
        self.assertIsNone(confirmation["conversationState"]["pendingAction"])
        self._assert_no_recommendations(confirmation)
        recommend.assert_not_called()

    @patch("main.recommend_from_matrix")
    def test_casual_surf_conversation_never_uses_recommendation_fallback(self, recommend):
        for message in ("Why do fish feel so fast?", "Thanks, that makes sense.", "What does a swallow tail do?"):
            with self.subTest(message=message):
                body = self.client.post("/api/board-guide/chat", json={"message": message, "region": "AU"}).json()
                self._assert_no_recommendations(body)
        recommend.assert_not_called()


if __name__ == "__main__":
    unittest.main()
