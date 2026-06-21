import unittest

from app.models import RiderProfile
from app.volume_engine_v2 import fish_volume_bands, recommend_volume_v2


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


if __name__ == "__main__":
    unittest.main()
