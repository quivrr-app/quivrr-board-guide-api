import unittest

from app.models import RiderProfile
from app.profile_engine import extract_profile_result, merge_rider_profile, profile_completeness, with_profile_source


class ProfileEngineTests(unittest.TestCase):
    def test_account_profile_is_base_but_conversation_overrides_it(self):
        account = with_profile_source(RiderProfile(region="AU", ability="Intermediate", weight_kg=82), "account_profile")
        existing = with_profile_source(RiderProfile(weight_kg=80), "conversation_profile")
        extracted = with_profile_source(RiderProfile(weight_kg=78, wave_power="Weak"), "current_user")

        merged = merge_rider_profile(existing, extracted, account_profile=account)

        self.assertEqual(merged.region, "AU")
        self.assertEqual(merged.ability, "Intermediate")
        self.assertEqual(merged.weight_kg, 78)
        self.assertEqual(merged.wave_power, "Weak")
        self.assertIn("account_profile", merged.profile_sources)
        self.assertIn("current_user", merged.profile_sources)
        self.assertEqual(merged.field_provenance["weight_kg"], "current_user")

    def test_conflicts_are_recorded_for_material_changes(self):
        existing = with_profile_source(RiderProfile(ability="Beginner", weight_kg=72), "conversation_profile")
        extracted = with_profile_source(RiderProfile(ability="Advanced", weight_kg=72), "conversation_user")

        merged = merge_rider_profile(existing, extracted)

        self.assertEqual(merged.ability, "Advanced")
        self.assertTrue(any("ability:" in item for item in merged.profile_conflicts))

    def test_extract_profile_result_captures_richer_fields(self):
        result = extract_profile_result(
            "I'm 75kg, 46, intermediate, goofy, surf 2 to 4ft reef breaks in Europe and want more paddle."
        )

        self.assertEqual(result.profile.weight_kg, 75)
        self.assertEqual(result.profile.age_band, "40s")
        self.assertEqual(result.profile.stance, "Goofy")
        self.assertEqual(result.profile.wave_type, "Reef Break")
        self.assertEqual(result.profile.wave_size_min_ft, 2.0)
        self.assertEqual(result.profile.wave_size_max_ft, 4.0)
        self.assertEqual(result.profile.region, "EU")
        self.assertGreater(result.confidence_by_field["weight_kg"], 0.8)
        self.assertEqual(result.profile.field_provenance["weight_kg"], "current_user")

    def test_weight_statement_does_not_get_mistaken_for_age(self):
        result = extract_profile_result("I am 72 kg and need an all rounder for Europe.", "EU")

        self.assertEqual(result.profile.weight_kg, 72)
        self.assertIsNone(result.profile.age)
        self.assertIsNone(result.profile.age_band)
        self.assertEqual(result.profile.region, "EU")

    def test_profile_completeness_reflects_recommendation_readiness(self):
        sparse = RiderProfile(weight_kg=75)
        rich = RiderProfile(
            weight_kg=75,
            ability="Intermediate",
            region="AU",
            wave_size_min_ft=2,
            wave_size_max_ft=4,
            wave_power="Weak",
        )

        self.assertLess(profile_completeness(sparse), 0.5)
        self.assertEqual(profile_completeness(rich), 1.0)

    def test_current_user_correction_replaces_previous_value_without_false_conflict(self):
        existing = with_profile_source(RiderProfile(weight_kg=75), "conversation_profile")
        extracted = with_profile_source(RiderProfile(weight_kg=78), "current_user")

        merged = merge_rider_profile(existing, extracted)

        self.assertEqual(merged.weight_kg, 78)
        self.assertFalse(any("weight_kg:" in item for item in merged.profile_conflicts))

    def test_current_user_correction_can_override_saved_profile_without_false_conflict(self):
        saved = with_profile_source(RiderProfile(current_volume_litres=28.6), "saved_profile")
        extracted = with_profile_source(RiderProfile(current_volume_litres=29.2), "current_user")

        merged = merge_rider_profile(saved, extracted)

        self.assertEqual(merged.current_volume_litres, 29.2)
        self.assertEqual(merged.field_provenance["current_volume_litres"], "current_user")
        self.assertFalse(any("current_volume_litres:" in item for item in merged.profile_conflicts))


if __name__ == "__main__":
    unittest.main()
