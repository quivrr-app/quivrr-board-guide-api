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


if __name__ == "__main__":
    unittest.main()
