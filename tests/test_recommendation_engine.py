import unittest

from app.models import RiderProfile
from app.model_recommendation_engine import recommend_models


class RecommendationEngineTests(unittest.TestCase):
    def test_recommendations_only_return_valid_catalogue_backed_models(self):
        rows = recommend_models(RiderProfile(
            weight_kg=75,
            ability="Intermediate",
            region="EU",
            wave_type="Beach Break",
            wave_power="Weak",
            preferred_board_type="Daily Driver",
        ), limit=5)

        self.assertTrue(rows)
        self.assertTrue(all(row.brand and row.model for row in rows))
        self.assertTrue(all(0 < row.confidence <= 0.98 for row in rows))


if __name__ == "__main__":
    unittest.main()
