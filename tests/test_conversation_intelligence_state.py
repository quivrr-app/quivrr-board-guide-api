import unittest

from app.conversation import ConversationManager


class ConversationIntelligenceStateTests(unittest.TestCase):
    def test_stage_answer_resolves_and_clears_clarification_without_losing_goal(self):
        manager = ConversationManager()
        state = manager.migrate_legacy({
            "activeRegion": "AU",
            "pendingClarification": {"question": "Can you catch green waves?"},
        })

        result = manager.apply_turn(state, "I can catch green waves sometimes and ride along the face.")

        self.assertTrue(result.clarification_resolved)
        self.assertIsNone(state.pending_clarification)
        self.assertEqual(state.surfer_stage.stage, "STAGE_2_PROGRESSING_BEGINNER")
        self.assertEqual(state.active_goal.type, "FIND_BOARD")
        self.assertEqual(state.active_region, "AU")

    def test_challenge_and_volume_refinement_preserve_stage_and_prefer_mid_length(self):
        manager = ConversationManager()
        state = manager.migrate_legacy({"activeRegion": "AU", "pendingClarification": {"question": "Can you catch green waves?"}})
        manager.apply_turn(state, "I can catch green waves sometimes")

        self.assertEqual(manager.apply_turn(state, "Wouldn't a mid-length be better?").relationship, "CHALLENGE")
        self.assertEqual(manager.apply_turn(state, "I need more volume.").relationship, "REFINEMENT")
        self.assertEqual(state.surfer_stage.stage, "STAGE_2_PROGRESSING_BEGINNER")
        self.assertEqual(state.active_recommendation.preferred_families[0], "FORGIVING_MID_LENGTH")
        self.assertEqual(state.active_recommendation.size_guidance["direction"], "MORE_VOLUME")
        self.assertIn("PERFORMANCE_FISH", state.active_recommendation.excluded_families)

    def test_inventory_ok_confirms_only_a_pending_inventory_action(self):
        manager = ConversationManager()
        state = manager.migrate_legacy({"activeRegion": "AU"})
        state.pending_action = state.pending_action.model_copy(update={"type": "CHECK_INVENTORY", "status": "AWAITING_CONFIRMATION"}) if state.pending_action else None
        if state.pending_action is None:
            from app.conversation.models import PendingInteraction
            state.pending_action = PendingInteraction(type="CHECK_INVENTORY", status="AWAITING_CONFIRMATION", arguments={"region": "AU"})
        result = manager.apply_turn(state, "OK")
        self.assertTrue(result.action_confirmed)
        self.assertIsNone(state.pending_action)
