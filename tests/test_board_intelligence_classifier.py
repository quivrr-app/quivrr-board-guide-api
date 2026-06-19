import unittest

from app.board_intelligence_classifier import classify_board


class BoardIntelligenceClassifierTests(unittest.TestCase):
    def test_pyzel_ghost_profile(self):
        result = classify_board({
            "brand": "Pyzel", "model": "Ghost",
            "model_description": "A high performance shortboard built for advanced surfers in hollow powerful waves.",
        })
        self.assertEqual(result["boardCategory"], "step_up")
        self.assertTrue(result["performanceShortboard"])
        self.assertTrue(result["stepUp"])
        self.assertTrue(result["advanced"])
        self.assertFalse(result["longboard"])
        self.assertEqual((result["waveRangeMinFt"], result["waveRangeMaxFt"]), (4.0, 12.0))
        self.assertIn("tube_riding", result["tags"])

    def test_hypto_krypto_profile(self):
        result = classify_board({
            "brand": "Haydenshapes", "model": "Hypto Krypto",
            "model_description": "A versatile everyday board that paddles easily and helps surfers stepping down from a longboard.",
        })
        self.assertEqual(result["boardCategory"], "hybrid")
        self.assertTrue(result["dailyDriver"])
        self.assertTrue(result["hybrid"])
        self.assertTrue(result["intermediate"])
        self.assertTrue(result["advanced"])
        self.assertFalse(result["longboard"])
        self.assertEqual((result["waveRangeMinFt"], result["waveRangeMaxFt"]), (2.0, 8.0))

    def test_js_monsta_profile(self):
        result = classify_board({
            "brand": "JS Industries", "model": "Monsta",
            "model_description": "A high-performance shortboard for advanced surfing.",
        })
        self.assertEqual(result["boardCategory"], "performance_shortboard")
        self.assertTrue(result["performanceShortboard"])
        self.assertTrue(result["dailyDriver"])
        self.assertEqual((result["waveRangeMinFt"], result["waveRangeMaxFt"]), (2.0, 8.0))

    def test_explicit_description_rules(self):
        result = classify_board({
            "brand": "Example", "model": "Board",
            "model_description": (
                "A daily driver hybrid shortboard for intermediate surfers. Works in weak waves "
                "from 2 to 6 feet at beach breaks and paddles easily for a higher wave count."
            ),
        })
        self.assertTrue(result["dailyDriver"])
        self.assertTrue(result["hybrid"])
        self.assertTrue(result["beachBreak"])
        self.assertTrue(result["weak"])
        self.assertEqual((result["waveRangeMinFt"], result["waveRangeMaxFt"]), (2.0, 6.0))
        self.assertIn("easy_paddling", result["tags"])
        self.assertIn("high_wave_count", result["tags"])

    def test_missing_description_is_not_fabricated(self):
        result = classify_board({"brand": "Example", "model": "Mystery"})
        self.assertEqual(result["boardCategory"], "unclassified")
        self.assertEqual(result["classificationConfidence"], 0)
        self.assertFalse(any(result[name] for name in [
            "dailyDriver", "performanceShortboard", "groveller", "fish", "stepUp",
            "midLength", "longboard", "twinFin", "hybrid",
        ]))

    def test_model_name_alone_does_not_trigger_weak_match(self):
        result = classify_board({"brand": "Example", "model": "Daily Fish", "model_description": "A surfboard."})
        self.assertEqual(result["boardCategory"], "unclassified")
        self.assertLess(result["classificationConfidence"], 0.5)


if __name__ == "__main__":
    unittest.main()
