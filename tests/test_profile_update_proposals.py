import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import main
from app.authenticated_profile import AuthenticatedProfileContext
from app.models import RiderProfile


class ProfileUpdateProposalTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)
        self.saved = AuthenticatedProfileContext(
            authenticated=True,
            profile_loaded=True,
            user_id="user-1",
            status="loaded",
            profile=RiderProfile(weight_kg=74, ability="Intermediate", region="AU", profile_sources=["saved_profile"]),
        )

    @patch("main.is_azure_openai_configured", return_value=False)
    @patch("main.load_authenticated_profile_context")
    def test_durable_weight_change_uses_current_context_then_requires_confirmation(self, profile_context, _azure):
        profile_context.return_value = self.saved
        first = self.client.post("/api/board-guide/chat", headers={"Authorization": "Bearer test"}, json={
            "message": "No, I am 76 kg now. Tell me about the JS Monsta.", "region": "ID",
        }).json()
        self.assertEqual(first["profile"]["weight_kg"], 76)
        self.assertEqual(first["profileUpdateProposal"]["fields"], {"weightKg": 76})
        self.assertEqual(first["conversationState"]["pendingProfileUpdate"]["fields"], {"weightKg": 76})

        confirmed = self.client.post("/api/board-guide/chat", headers={"Authorization": "Bearer test"}, json={
            "message": "Yes", "region": "ID", "conversationState": first["conversationState"],
        }).json()
        self.assertTrue(confirmed["profileUpdateConfirmationRequested"])
        self.assertEqual(confirmed["profileUpdateProposal"]["fields"], {"weightKg": 76})
        self.assertIsNone(confirmed["conversationState"]["pendingProfileUpdate"])

    @patch("main.is_azure_openai_configured", return_value=False)
    @patch("main.load_authenticated_profile_context")
    def test_temporary_travel_context_never_creates_a_saved_profile_proposal(self, profile_context, _azure):
        profile_context.return_value = self.saved
        response = self.client.post("/api/board-guide/chat", headers={"Authorization": "Bearer test"}, json={
            "message": "I am surfing Indonesia this week. Tell me about the JS Monsta.", "region": "ID",
        }).json()
        self.assertEqual(response["profile"]["region"], "ID")
        self.assertIsNone(response.get("profileUpdateProposal"))

    @patch("main.is_azure_openai_configured", return_value=False)
    @patch("main.load_authenticated_profile_context")
    def test_explicit_volume_change_outranks_previous_inventory_context(self, profile_context, _azure):
        profile_context.return_value = AuthenticatedProfileContext(
            authenticated=True,
            profile_loaded=True,
            user_id="user-1",
            status="loaded",
            profile=RiderProfile(weight_kg=74, ability="Intermediate", region="AU", current_volume_litres=28.6),
        )
        response = self.client.post("/api/board-guide/chat", headers={"Authorization": "Bearer test"}, json={
            "message": "can you change my volume to 31lts please?",
            "region": "ID",
            "conversationState": {
                "lastIntent": "AVAILABILITY",
                "activeRegion": "ID",
                "activeBoard": {"brand": "Album", "model": "Plasmic", "boardModelId": 205, "canonicalKey": "album|plasmic"},
            },
        }).json()
        self.assertEqual(response["intent"], "profile_update_request")
        self.assertEqual(response["profileUpdateProposal"]["fields"], {"currentVolumeLitres": 31.0})
        self.assertEqual(response["profileUpdateProposal"]["currentValues"], {"currentVolumeLitres": 28.6})
        self.assertIn("saved My Quivrr", response["reply"])


if __name__ == "__main__":
    unittest.main()
