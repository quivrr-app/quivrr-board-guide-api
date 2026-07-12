import hashlib
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
        self.assertTrue(all(row.get("broadFamily") for row in boards))
        self.assertTrue(all(row.get("designSubtype") for row in boards))

    def test_crossovers_and_reviewed_examples(self):
        phantom = find_matrix_board("Pyzel", "Phantom")
        hypto = find_matrix_board("Haydenshapes", "Hypto Krypto")
        rnf = find_matrix_board("Lost", "RNF 96")
        self.assertEqual(phantom["primaryLane"], "performance_daily_driver")
        self.assertIn("one_board_quiver", phantom["secondaryLanes"])
        self.assertEqual(hypto["primaryLane"], "hybrid_daily_driver")
        self.assertIn("forgiving_daily_driver", hypto["secondaryLanes"])
        self.assertEqual(rnf["primaryLane"], "modern_fish")
        self.assertIn("twin_fin_performance", rnf["secondaryLanes"])

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
        self.assertEqual(target_lanes(profile), [
            "modern_fish", "performance_fish", "traditional_fish", "cruisy_fish",
        ])
        rows = recommend_from_matrix(profile, limit=20)
        self.assertTrue(rows)
        self.assertTrue(any("fish" in row.category.lower() or "twin" in row.category.lower() for row in rows))

    def test_phase8_curated_overrides_and_iconic_fish_sublanes(self):
        audit = json.loads(generator.PHASE8_AUDIT_JSON_PATH.read_text(encoding="utf-8"))
        self.assertGreaterEqual(audit["totalCuratedOverrides"], 100)
        self.assertGreater(audit["highConfidenceOverrides"], 0)
        expectations = {
            ("Album", "Lightbender"): {"performance_fish", "modern_fish", "point_break_fish"},
            ("Album", "Twinsman"): {"twin_fin_performance", "modern_fish", "point_break_fish"},
            ("Christenson", "Ocean Racer"): {"traditional_fish", "point_break_fish"},
            ("Firewire", "Seaside"): {"cruisy_fish", "small_wave_fish"},
            ("JS Industries", "Black Baron"): {"performance_fish", "small_wave_fish"},
            ("Lost", "RNF 96"): {"modern_fish", "small_wave_fish"},
        }
        for identity, required in expectations.items():
            with self.subTest(board=identity):
                row = find_matrix_board(*identity)
                lanes = {row["primaryLane"], *row["secondaryLanes"], *row["boardLanes"]}
                self.assertTrue(required <= lanes)

    def test_point_break_fish_profile_prioritises_point_lane(self):
        profile = RiderProfile(preferred_board_type="Fish", wave_type="Point Break", ability="Intermediate")
        self.assertEqual(target_lanes(profile)[0], "point_break_fish")
        rows = recommend_from_matrix(profile, limit=12)
        self.assertTrue(any(row.model in {"Ocean Racer", "Lightbender", "Twinsman", "RNF 96"} for row in rows))

    def test_reef_fish_profile_prioritises_performance_fish_and_twin_lanes(self):
        profile = RiderProfile(
            preferred_board_type="Fish",
            wave_type="Reef Break",
            wave_power="Average to Powerful",
            ability="Advanced",
            goal="Performance progression",
            target_volume_litres=28.6,
        )
        self.assertEqual(
            target_lanes(profile)[:4],
            ["performance_fish", "point_break_fish", "twin_fin_performance", "modern_fish"],
        )
        rows = recommend_from_matrix(profile, limit=8)
        self.assertTrue(rows)
        top_categories = [row.category for row in rows[:4]]
        self.assertTrue(any(category in {"Performance Fish", "Performance Twin"} for category in top_categories))
        self.assertFalse(all(category == "Fish" for category in top_categories))

    def test_bom_dia_is_classified_as_performance_twin(self):
        bom_dia = find_matrix_board("Album", "Bom Dia")
        self.assertEqual(bom_dia["broadFamily"], "Alternative")
        self.assertEqual(bom_dia["primaryFamily"], "Performance Twin")
        self.assertEqual(bom_dia["designSubtype"], "Alternative Performance Twin")
        self.assertEqual(bom_dia["variantType"], "standard")
        self.assertIn("Twin", bom_dia["finSetup"])

    def test_strict_hpsb_excludes_bom_dia_and_ghost_xl_for_light_advanced_rider(self):
        profile = RiderProfile(
            age=45,
            weight_kg=75,
            ability="Advanced",
            current_volume_litres=28.6,
            target_volume_litres=28.6,
            preferred_board_type="True performance shortboard",
            goal="Performance progression",
            wave_power="Powerful",
            surf_frequency_per_week=3,
            fitness_level="Good",
            paddle_strength="Good",
        )
        rows = recommend_from_matrix(profile, limit=12)
        names = {(row.brand, row.model) for row in rows}
        self.assertIn(("JS Industries", "Monsta"), names)
        self.assertNotIn(("Album", "Bom Dia"), names)
        self.assertNotIn(("Pyzel", "Ghost XL"), names)

    def test_heavier_rider_can_receive_supportive_xl_variant(self):
        profile = RiderProfile(
            age=48,
            weight_kg=92,
            ability="Advanced",
            preferred_board_type="Performance shortboard",
            goal="More paddle support",
            wave_power="Powerful",
            surf_frequency_per_week=1,
            fitness_level="Average",
            paddle_strength="Average",
            target_volume_litres=33.5,
        )
        rows = recommend_from_matrix(profile, limit=12)
        self.assertTrue(any(row.model == "Ghost XL" for row in rows))

    def test_forgiving_performance_request_prefers_daily_drivers(self):
        profile = RiderProfile(
            age=45,
            weight_kg=75,
            ability="Intermediate",
            preferred_board_type="Performance shortboard",
            goal="Something more forgiving and performance focused",
            surf_frequency_per_week=0.25,
            fitness_level="Average",
            paddle_strength="Average",
        )
        rows = recommend_from_matrix(profile, limit=8)
        self.assertTrue(rows)
        self.assertIn(rows[0].category, {"Performance Daily Driver", "Daily Driver", "Hybrid Shortboard"})

    def test_generation_is_deterministic(self):
        before = hashlib.sha256(generator.OUTPUT_PATH.read_bytes()).hexdigest()
        generator.main()
        after = hashlib.sha256(generator.OUTPUT_PATH.read_bytes()).hexdigest()
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
