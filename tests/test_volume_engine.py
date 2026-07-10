import unittest

from app.models import RiderProfile
from app.volume_engine_v2 import build_volume_recommendation, recommend_volume_v2


class VolumeEngineTests(unittest.TestCase):
    def test_intermediate_weak_wave_profile_returns_structured_volume_output(self):
        recommendation = build_volume_recommendation(RiderProfile(
            weight_kg=75,
            ability="Intermediate",
            wave_power="Weak",
            preferred_board_type="Daily Driver",
        ))

        self.assertIsNotNone(recommendation)
        self.assertGreater(recommendation.target_midpoint_litres, 0)
        self.assertLessEqual(recommendation.performance_min_litres, recommendation.target_midpoint_litres)
        self.assertGreaterEqual(recommendation.forgiving_max_litres, recommendation.comfortable_max_litres)
        self.assertIn("outline, width, rocker", recommendation.explanation)

    def test_missing_weight_returns_no_volume_recommendation(self):
        self.assertIsNone(build_volume_recommendation(RiderProfile(ability="Intermediate")))

    def test_current_board_volume_influences_target(self):
        baseline = build_volume_recommendation(RiderProfile(weight_kg=75, ability="Intermediate"))
        anchored = build_volume_recommendation(RiderProfile(
            weight_kg=75,
            ability="Intermediate",
            current_volume_litres=33,
        ))

        self.assertGreaterEqual(anchored.target_midpoint_litres, baseline.target_midpoint_litres)

    def test_weak_waves_need_more_volume_than_powerful_waves(self):
        weak = recommend_volume_v2(RiderProfile(weight_kg=75, ability="Intermediate", wave_power="Weak"))
        powerful = recommend_volume_v2(RiderProfile(weight_kg=75, ability="Intermediate", wave_power="Powerful"))
        self.assertGreater(weak.target_volume, powerful.target_volume)
        self.assertTrue(any("weak-wave" in reason.lower() for reason in weak.reasoning))

    def test_weak_paddle_strength_needs_more_volume_than_strong_paddle_strength(self):
        weak = recommend_volume_v2(RiderProfile(weight_kg=75, ability="Intermediate", paddle_strength="Weak"))
        strong = recommend_volume_v2(RiderProfile(weight_kg=75, ability="Intermediate", paddle_strength="Strong"))
        self.assertGreater(weak.target_volume, strong.target_volume)
        self.assertTrue(any("paddle strength" in reason.lower() for reason in weak.reasoning))

    def test_current_board_feedback_changes_target(self):
        too_small = recommend_volume_v2(RiderProfile(
            weight_kg=75,
            ability="Intermediate",
            current_volume_litres=28,
            current_board_feedback="too small, hard to paddle",
        ))
        too_big = recommend_volume_v2(RiderProfile(
            weight_kg=75,
            ability="Intermediate",
            current_volume_litres=32,
            current_board_feedback="too big, too corky",
        ))
        self.assertGreater(too_small.target_volume, too_big.target_volume)
        self.assertTrue(any("under-volumed" in reason.lower() for reason in too_small.reasoning))
        self.assertTrue(any("over-volumed" in reason.lower() for reason in too_big.reasoning))

    def test_forgiving_brief_keeps_more_volume_than_high_performance_brief(self):
        forgiving = recommend_volume_v2(RiderProfile(weight_kg=75, ability="Intermediate", desired_feel="Forgiving"))
        performance = recommend_volume_v2(RiderProfile(weight_kg=75, ability="Intermediate", desired_feel="High Performance"))
        self.assertGreater(forgiving.target_volume, performance.target_volume)

    def test_missing_weight_but_known_current_volume_still_returns_range(self):
        recommendation = build_volume_recommendation(RiderProfile(
            ability="Intermediate",
            current_volume_litres=31,
        ))
        self.assertIsNotNone(recommendation)
        self.assertEqual(recommendation.target_midpoint_litres, 31)


if __name__ == "__main__":
    unittest.main()
