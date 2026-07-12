from __future__ import annotations

import json
from pathlib import Path
import unittest

from app.board_expert_matrix import recommend_from_matrix
from app.models import RiderProfile


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "bodhi_expert_expectations.json"


class BodhiRecommendationCalibrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scenarios = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    def test_fixture_contains_reviewed_expectations(self):
        self.assertGreaterEqual(len(self.scenarios), 40)

    def test_recommendation_expectations(self):
        for scenario in self.scenarios:
            with self.subTest(scenario=scenario["id"]):
                rows = recommend_from_matrix(RiderProfile.model_validate(scenario["profile"]), limit=8)
                self.assertTrue(rows, f"No recommendations returned for {scenario['id']}")

                categories = {row.category for row in rows[:6]}
                allowed = set(scenario.get("allowed_families", []))
                excluded = set(scenario.get("excluded_families", []))
                if allowed:
                    self.assertTrue(categories <= allowed, f"{scenario['id']} categories drifted: {sorted(categories - allowed)}")
                if excluded:
                    self.assertTrue(categories.isdisjoint(excluded), f"{scenario['id']} included excluded families: {sorted(categories & excluded)}")

                names = {row.model for row in rows}
                for model in scenario.get("required_models", []):
                    self.assertIn(model, names, f"{scenario['id']} missing required model {model}")
                for model in scenario.get("excluded_models", []):
                    self.assertNotIn(model, names, f"{scenario['id']} included excluded model {model}")

                variant_preference = scenario.get("variant_preference")
                if variant_preference == "prefer_standard":
                    self.assertFalse(any(row.model.endswith("XL") for row in rows[:4]), f"{scenario['id']} elevated an XL variant too early")
                elif variant_preference == "prefer_xl":
                    self.assertTrue(any(row.model.endswith("XL") for row in rows[:6]), f"{scenario['id']} did not surface an XL-supporting option")

                explanation = " ".join(row.why_it_fits.lower() for row in rows[:3])
                for theme in scenario.get("explanation_themes", []):
                    self.assertIn(theme.lower(), explanation, f"{scenario['id']} explanation missed {theme}")


if __name__ == "__main__":
    unittest.main()
