import unittest

from app.board_fit_engine import score_board_fit
from app.board_intelligence import find_board_record
from app.models import RiderProfile


class BoardFitScoringTests(unittest.TestCase):
    def test_daily_driver_brief_prefers_phantom_over_hypto_for_good_waves(self):
        profile = RiderProfile(
            weight_kg=75,
            ability="Advanced",
            wave_power="Average to Powerful",
            preferred_board_type="Daily Driver",
        )
        phantom = score_board_fit(find_board_record("Pyzel", "Phantom"), profile)
        hypto = score_board_fit(find_board_record("Haydenshapes", "Hypto Krypto"), profile)
        self.assertGreater(phantom.score.total, hypto.score.total)

    def test_hard_exclusions_reject_step_ups_for_weak_daily_driver_brief(self):
        profile = RiderProfile(
            weight_kg=75,
            ability="Intermediate",
            wave_power="Weak",
            preferred_board_type="Daily Driver",
        )
        board = find_board_record("Pyzel", "Ghost Swallow")
        fit = score_board_fit(board, profile)
        self.assertTrue(fit.hard_exclusions)

    def test_size_match_uses_target_volume_when_available(self):
        profile = RiderProfile(
            weight_kg=75,
            ability="Intermediate",
            target_volume_litres=30,
        )
        board = find_board_record("Firewire", "Seaside")
        fit = score_board_fit(board, profile)
        self.assertIsNotNone(fit.size_match.size)
        self.assertLessEqual(abs((fit.size_match.size.volume_litres or 0) - 30), 2.5)


if __name__ == "__main__":
    unittest.main()
