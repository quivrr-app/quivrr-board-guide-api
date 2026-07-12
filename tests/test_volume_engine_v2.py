import unittest

from app.models import RiderProfile
from app.volume_engine_v2 import build_target_volume_context, fish_volume_bands, recommend_volume_v2


class VolumeEngineV2Tests(unittest.TestCase):
    def profile(self, **updates):
        base = RiderProfile(weight_kg=76, age=46, fitness_level="High", ability="Intermediate")
        return base.model_copy(update=updates)

    def test_board_type_changes_volume_band(self):
        shortboard = recommend_volume_v2(self.profile(), "performance_shortboard")
        fish = recommend_volume_v2(self.profile(), "performance_fish")
        self.assertEqual(shortboard.volume_band_label, "28 to 31L")
        self.assertEqual(fish.volume_band_label, "30.5 to 34L")
        self.assertGreater(fish.target_volume, shortboard.target_volume)

    def test_traditional_fish_carries_more_than_performance_fish(self):
        bands = fish_volume_bands(self.profile())
        self.assertEqual(bands["traditional_fish"].volume_band_label, "32 to 36L")
        self.assertEqual(bands["point_break_fish"].volume_band_label, "31 to 35L")
        self.assertGreater(bands["traditional_fish"].target_volume, bands["performance_fish"].target_volume)

    def test_current_volume_anchors_target(self):
        baseline = recommend_volume_v2(self.profile(), "performance_fish")
        anchored = recommend_volume_v2(self.profile(current_volume_litres=36), "performance_fish")
        self.assertGreater(anchored.target_volume, baseline.target_volume)
        self.assertTrue(any("current 36L" in reason for reason in anchored.reasoning))

    def test_age_alone_does_not_add_volume_for_fit_surfer(self):
        younger = recommend_volume_v2(self.profile(age=30), "performance_fish")
        older_fit = recommend_volume_v2(self.profile(age=55), "performance_fish")
        self.assertEqual(younger.volume_band_label, older_fit.volume_band_label)

    def test_saved_profile_current_volume_builds_tight_performance_fish_target_context(self):
        profile = RiderProfile(
            weight_kg=75,
            ability="Advanced",
            current_volume_litres=28.6,
            target_volume_litres=28.6,
            target_volume_source="saved_profile",
            target_volume_confidence="high",
            fieldProvenance={"current_volume_litres": "saved_profile", "target_volume_litres": "saved_profile"},
        )

        context = build_target_volume_context(profile, "performance_fish")

        self.assertIsNotNone(context)
        self.assertEqual(context.target_litres, 28.6)
        self.assertEqual(context.minimum_litres, 27.5)
        self.assertEqual(context.maximum_litres, 30.5)
        self.assertEqual(context.source, "saved_profile")
        self.assertEqual(context.confidence, "high")

    def test_explicit_saved_profile_volume_range_is_preserved(self):
        profile = RiderProfile(
            target_volume_litres=28.6,
            target_volume_min_litres=27.5,
            target_volume_max_litres=30.5,
            target_volume_source="saved_profile",
            target_volume_confidence="high",
            fieldProvenance={"target_volume_litres": "saved_profile"},
        )

        context = build_target_volume_context(profile, "performance_fish")

        self.assertEqual(context.target_litres, 28.6)
        self.assertEqual(context.minimum_litres, 27.5)
        self.assertEqual(context.maximum_litres, 30.5)


if __name__ == "__main__":
    unittest.main()
