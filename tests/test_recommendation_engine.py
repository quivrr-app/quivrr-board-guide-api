import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.board_intelligence import BoardIntelligenceRecord
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

    @staticmethod
    def _board(brand, model, **overrides):
        return BoardIntelligenceRecord(
            brand=brand,
            model=model,
            board_model_id=None,
            category="daily_driver",
            primary_category="daily_driver",
            lane="performance_daily_driver",
            description="Board description",
            short_description="Board short description",
            official_product_url=None,
            source_type="canonical_catalogue",
            source_confidence=0.95,
            curated=False,
            graph_eligible=True,
            classified=True,
            unclassified=False,
            **overrides,
        )

    @staticmethod
    def _fit(total, *, evidence=0.8, goal=0.8):
        return SimpleNamespace(
            hard_exclusions=[],
            reasons=("fits the rider",),
            size_match=SimpleNamespace(size=None),
            score=SimpleNamespace(total=total, evidence_quality=evidence, goal_fit=goal),
        )

    @patch("app.model_recommendation_engine.score_board_fit")
    @patch("app.model_recommendation_engine.load_board_records")
    def test_newer_model_wins_close_fit_tie_break(self, load_records, score_fit):
        newer = self._board("Pyzel", "Shadow", release_year=2025, is_current_model=True)
        older = self._board("Pyzel", "Ghost", release_year=2018, is_current_model=False)
        load_records.return_value = (older, newer)
        score_fit.side_effect = [self._fit(8.0), self._fit(8.0)]

        rows = recommend_models(RiderProfile(weight_kg=75, ability="Intermediate", region="US"), limit=2)

        self.assertEqual([row.model for row in rows[:2]], ["Shadow", "Ghost"])

    @patch("app.model_recommendation_engine.score_board_fit")
    @patch("app.model_recommendation_engine.load_board_records")
    def test_older_model_stays_first_when_fit_is_clearly_better(self, load_records, score_fit):
        newer = self._board("Pyzel", "Shadow", release_year=2025, is_current_model=True)
        older = self._board("Pyzel", "Ghost", release_year=2018, is_current_model=False)
        load_records.return_value = (older, newer)
        score_fit.side_effect = [self._fit(8.8), self._fit(8.1)]

        rows = recommend_models(RiderProfile(weight_kg=75, ability="Intermediate", region="US"), limit=2)

        self.assertEqual([row.model for row in rows[:2]], ["Ghost", "Shadow"])

    @patch("app.model_recommendation_engine.score_board_fit")
    @patch("app.model_recommendation_engine.load_board_records")
    def test_regional_brand_affinity_breaks_close_scores(self, load_records, score_fit):
        js = self._board("JS Industries", "Xero Gravity")
        album = self._board("Album", "Disorder")
        load_records.return_value = (album, js)
        score_fit.side_effect = [self._fit(8.0), self._fit(8.0), self._fit(8.0), self._fit(8.0)]

        au_rows = recommend_models(RiderProfile(weight_kg=75, ability="Intermediate", region="AU"), limit=2)
        us_rows = recommend_models(RiderProfile(weight_kg=75, ability="Intermediate", region="US"), limit=2)

        self.assertEqual(au_rows[0].brand, "JS Industries")
        self.assertEqual(us_rows[0].brand, "Album")

    @patch("app.model_recommendation_engine.score_board_fit")
    @patch("app.model_recommendation_engine.load_board_records")
    def test_preferred_brand_beats_other_close_options(self, load_records, score_fit):
        pyzel = self._board("Pyzel", "Phantom")
        ci = self._board("Channel Islands", "Happy Everyday")
        load_records.return_value = (ci, pyzel)
        score_fit.side_effect = [self._fit(8.0), self._fit(8.0)]

        rows = recommend_models(
            RiderProfile(weight_kg=75, ability="Intermediate", region="EU", preferred_brands=["Pyzel"]),
            limit=2,
        )

        self.assertEqual(rows[0].brand, "Pyzel")


if __name__ == "__main__":
    unittest.main()
