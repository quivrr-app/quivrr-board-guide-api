import unittest

from app.conversation_flow import comparison_reply
from app.comparison_engine import compare_board_models
from app.models import RiderProfile


class BoardComparisonsTests(unittest.TestCase):
    def test_required_comparison_pairs_publish_governed_dna(self):
        pairs = (
            ("Christenson", "Fish", "Christenson", "Carrera"),
            ("Christenson", "Acid Phish", "Christenson", "Lane Splitter"),
            ("Christenson", "OP4", "Christenson", "Carrera"),
            ("Christenson", "Osprey", "Christenson", "Long Phish II"),
            ("Christenson", "Easy Wind", "Christenson", "Cafe Racer"),
            ("Pyzel", "Ghost", "Pyzel", "Phantom"),
            ("Pyzel", "Gremlin", "Pyzel", "Ghost"),
        )
        expected_metrics = {
            "paddle", "speed_generation", "drive", "release", "hold",
            "forgiveness", "sensitivity",
        }
        for left_brand, left_model, right_brand, right_model in pairs:
            with self.subTest(left=left_model, right=right_model):
                result = compare_board_models(
                    left_brand, left_model, right_brand, right_model,
                    RiderProfile(ability="advanced", region="AU"),
                )
                self.assertIsNotNone(result)
                for dna in (result.comparison.board_a_dna, result.comparison.board_b_dna):
                    self.assertTrue(dna["family"])
                    self.assertTrue(dna["detailed_category"])
                    self.assertEqual(set(dna["behaviour"]), expected_metrics)
                    self.assertEqual(len(dna["wave_context"]), 8)
                    self.assertIsInstance(dna["ability_fit"], int)
                    self.assertTrue(dna["quiver_roles"])
                self.assertTrue(result.comparison.dna_tradeoffs)

    def test_comparison_reply_uses_controlled_board_names(self):
        reply = comparison_reply(
            "Compare Pyzel Phantom and JS Monsta",
            profile=RiderProfile(weight_kg=75, region="EU", wave_type="Beach Break"),
        )

        self.assertIn("Pyzel Phantom", reply)
        self.assertIn("JS Industries Monsta", reply)

    def test_governed_christenson_comparisons_explain_design_contract(self):
        pairs = (
            ("Fish", "Carrera"),
            ("Lane Splitter", "Acid Phish"),
            ("OP4", "Carrera"),
            ("Osprey", "Long Phish II"),
            ("Easy Wind", "Cafe Racer"),
        )
        for left, right in pairs:
            with self.subTest(left=left, right=right):
                reply = comparison_reply(
                    f"Compare Christenson {left} versus {right}",
                    boards=[
                        {"brand": "Christenson", "model": left},
                        {"brand": "Christenson", "model": right},
                    ],
                    profile=RiderProfile(region="AU"),
                )
                self.assertIn(f"Christenson {left}", reply)
                self.assertIn(f"Christenson {right}", reply)
                self.assertIn("Category difference:", reply)
                self.assertIn("wave intent:", reply)
                self.assertIn("fin setup:", reply)
                self.assertIn("Trade-off:", reply)


if __name__ == "__main__":
    unittest.main()
