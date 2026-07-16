import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import main
from app.board_fit_engine import score_board_fit
from app.board_intelligence import find_board_record
from app.model_recommendation_engine import build_recommendation_context, recommend_models
from app.models import RiderProfile


class Slice2GuardTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)

    def test_hard_exclusion_blocks_step_up_for_weak_daily_driver_brief(self):
        fit = score_board_fit(
            find_board_record("Pyzel", "Ghost Swallow"),
            RiderProfile(
                weight_kg=75,
                ability="Intermediate",
                wave_power="Weak",
                preferred_board_type="Daily Driver",
            ),
        )
        self.assertTrue(fit.hard_exclusions)
        self.assertTrue(
            any(
                reason in fit.hard_exclusions
                for reason in [
                    "outside the daily-driver lane",
                    "step-up boards are out of scope for weak surf",
                    "high-performance shortboards are out of scope for a weak-wave daily-driver brief",
                ]
            )
        )

    def test_recommendation_context_explicitly_forbids_inventing_or_reordering(self):
        rows = recommend_models(
            RiderProfile(
                weight_kg=75,
                ability="Advanced",
                wave_power="Average to Powerful",
                preferred_board_type="Daily Driver",
            ),
            limit=3,
        )
        context = build_recommendation_context(rows)
        self.assertIn("Do not invent, reorder, or replace model names.", context)

    @patch("main.enrich_suggestions_with_inventory", side_effect=lambda rows, profile: rows)
    def test_api_comparison_contract_returns_structured_comparison(self, _inventory):
        response = self.client.post("/api/board-guide/chat", json={
            "message": "Compare Pyzel Phantom and JS Monsta",
            "profile": {"weight_kg": 75, "ability": "Advanced", "preferred_board_type": "Daily Driver"},
        })
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["intent"], "comparison_request")
        self.assertIsNotNone(body["comparison"])
        self.assertEqual(body["comparison"]["board_a"]["model"], "Phantom")
        self.assertEqual(body["comparison"]["board_b"]["model"], "Monsta")
        self.assertTrue(body["comparison"]["rider_specific_conclusion"])

    @patch("main.locate_exact_board", return_value=([], False))
    @patch("main.enrich_suggestions_with_inventory", side_effect=lambda rows, profile: rows)
    def test_unavailable_exact_board_does_not_invent_links_or_stock(self, _inventory, _locate):
        response = self.client.post("/api/board-guide/chat", json={
            "message": "Where can I buy a Christenson Fish in Australia?",
            "region": "AU",
        })
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["intent"], "exact_board_location_request")
        self.assertEqual(body["recommendations"], [])
        self.assertIn("can’t see that exact Christenson Fish", body["reply"])


if __name__ == "__main__":
    unittest.main()
