import hashlib
import json
import unittest

from app.board_expert_matrix import find_matrix_board, recommend_from_matrix, target_lanes
from app.models import RiderProfile
from scripts import generate_board_expert_matrix as generator


class BoardExpertMatrixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        generator.main()
        cls.payload = json.loads(generator.OUTPUT_PATH.read_text(encoding="utf-8"))

    def test_matrix_covers_all_canonical_models_with_primary_lanes(self):
        boards = self.payload["boards"]
        self.assertEqual(len(boards), 513)
        self.assertEqual(len({(row["brand"].lower(), row["model"].lower()) for row in boards}), 513)
        self.assertTrue(all(row["primaryLane"] for row in boards))

    def test_crossovers_and_reviewed_examples(self):
        phantom = find_matrix_board("Pyzel", "Phantom")
        hypto = find_matrix_board("Haydenshapes", "Hypto Krypto")
        rnf = find_matrix_board("Lost", "RNF 96")
        self.assertEqual(phantom["primaryLane"], "performance_daily_driver")
        self.assertIn("one_board_quiver", phantom["secondaryLanes"])
        self.assertEqual(hypto["primaryLane"], "hybrid_daily_driver")
        self.assertIn("forgiving_daily_driver", hypto["secondaryLanes"])
        self.assertEqual(rnf["primaryLane"], "fish")
        self.assertIn("twin_fin", rnf["secondaryLanes"])

    def test_matrix_supports_every_required_lane(self):
        required = {
            "performance_daily_driver", "forgiving_daily_driver", "hybrid_daily_driver",
            "small_wave_daily_driver", "high_performance_shortboard", "groveller", "fish",
            "twin_fin", "step_up", "gun", "mid_length", "longboard", "softboard", "youth",
            "foil", "beginner_progression", "one_board_quiver", "travel_board",
            "weak_wave_board", "powerful_wave_board",
        }
        actual = {lane for row in self.payload["boards"] for lane in [row["primaryLane"], *row["secondaryLanes"]]}
        self.assertTrue(required <= actual)

    def test_phantom_and_hypto_expert_tradeoff(self):
        phantom = find_matrix_board("Pyzel", "Phantom")
        hypto = find_matrix_board("Haydenshapes", "Hypto Krypto")
        self.assertGreater(phantom["goodWaveScore"], hypto["goodWaveScore"])
        self.assertGreater(hypto["forgivenessScore"], phantom["forgivenessScore"])
        self.assertGreater(hypto["oneBoardQuiverScore"], phantom["oneBoardQuiverScore"] - 1)

    def test_fish_profile_searches_crossover_lanes(self):
        profile = RiderProfile(preferred_board_type="Fish", target_volume_litres=30)
        self.assertEqual(target_lanes(profile), ["fish", "twin_fin", "small_wave_daily_driver"])
        rows = recommend_from_matrix(profile, limit=20)
        self.assertTrue(rows)
        self.assertTrue(any("Fish" in row.category or "Twin" in row.category for row in rows))

    def test_generation_is_deterministic(self):
        before = hashlib.sha256(generator.OUTPUT_PATH.read_bytes()).hexdigest()
        generator.main()
        after = hashlib.sha256(generator.OUTPUT_PATH.read_bytes()).hexdigest()
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
