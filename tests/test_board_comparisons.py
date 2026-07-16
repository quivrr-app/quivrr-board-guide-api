import unittest

from app.conversation_flow import comparison_reply
from app.models import RiderProfile


class BoardComparisonsTests(unittest.TestCase):
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
