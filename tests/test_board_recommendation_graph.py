import hashlib
import json
import unittest

from app.board_graph_engine import (
    ALLOWED_CATEGORIES, available_replacements, board_key, compare_boards, find_board,
)
from app.rider_archetypes import recommend_archetype_volume
from scripts import generate_board_recommendation_graph as generator


class BoardRecommendationGraphTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        generator.main()
        cls.graph = json.loads(generator.GRAPH_PATH.read_text(encoding="utf-8"))

    def test_taxonomy_examples(self):
        expected = {
            ("Haydenshapes", "Hypto Krypto"): ("hybrid", ["daily_driver"]),
            ("Pyzel", "Ghost"): ("step_up", ["performance_shortboard"]),
            ("JS Industries", "Monsta"): ("performance_shortboard", ["daily_driver"]),
            ("Lost", "RNF 96"): ("fish", ["groveller"]),
            ("Firewire", "Seaside"): ("fish", ["hybrid"]),
        }
        for identity, (primary, secondary) in expected.items():
            with self.subTest(identity=identity):
                board = find_board(self.graph, *identity)
                self.assertEqual(board["taxonomy"]["primaryCategory"], primary)
                self.assertEqual(board["taxonomy"]["secondaryCategories"], secondary)

    def test_graph_is_canonical_and_has_no_self_edges(self):
        boards = self.graph["boards"]
        self.assertEqual(len(boards), 518)
        identities = {board_key(row["brand"], row["model"]) for row in boards}
        self.assertEqual(len(identities), 518)
        for board in boards:
            self.assertIn(board["taxonomy"]["primaryCategory"], ALLOWED_CATEGORIES)
            for edges in board["recommendations"].values():
                for edge in edges:
                    self.assertIn(board_key(edge["brand"], edge["model"]), identities)
                    self.assertNotEqual(board_key(edge["brand"], edge["model"]), board_key(board["brand"], board["model"]))
                    self.assertIn(edge["confidence"], {"low", "medium", "high"})
                    self.assertTrue(edge["reason"])

    def test_monsta_reviewed_relationships(self):
        monsta = find_board(self.graph, "JS Industries", "Monsta")
        similar = {(row["brand"], row["model"]) for row in monsta["recommendations"]["similarBoards"]}
        self.assertTrue({("Pyzel", "Phantom"), ("Sharp Eye", "Inferno 72"), ("Channel Islands", "happy-everyday")} <= similar)
        self.assertEqual((monsta["recommendations"]["upgradeBoards"][0]["brand"], monsta["recommendations"]["upgradeBoards"][0]["model"]), ("Pyzel", "Ghost"))

    def test_available_replacements_put_selected_region_stock_first(self):
        availability = {
            board_key("Pyzel", "Phantom"): [{"RegionCode": "EU", "IsAvailable": True}],
            board_key("Sharp Eye", "Inferno 72"): [{"RegionCode": "AU", "IsAvailable": True}],
        }
        rows = available_replacements(self.graph, "JS Industries", "Monsta", 28.0, "EU", availability)
        self.assertEqual((rows[0]["brand"], rows[0]["model"]), ("Pyzel", "Phantom"))
        self.assertTrue(rows[0]["isAvailable"])
        inferno = next(row for row in rows if row["brand"] == "Sharp Eye" and row["model"] == "Inferno 72")
        self.assertFalse(inferno["isAvailable"])
        self.assertEqual(inferno["region"], "EU")

    def test_comparison_engine(self):
        result = compare_boards(self.graph, "Pyzel", "Ghost", "JS Industries", "Monsta")
        self.assertEqual(result["left"]["performanceBias"], "high")
        self.assertEqual(result["left"]["forgiveness"], "low")
        self.assertEqual(result["right"]["category"]["primaryCategory"], "performance_shortboard")
        self.assertIn("recommendedSurfer", result["left"])

    def test_graph_generation_is_deterministic(self):
        before = hashlib.sha256(generator.GRAPH_PATH.read_bytes()).hexdigest()
        generator.main()
        after = hashlib.sha256(generator.GRAPH_PATH.read_bytes()).hexdigest()
        self.assertEqual(before, after)


class RiderArchetypeTests(unittest.TestCase):
    def test_deterministic_volume_guidance(self):
        result = recommend_archetype_volume(
            height_cm=180, weight_kg=75, skill="intermediate", fitness="average",
            sessions_per_week=2, age=35,
        )
        self.assertEqual((result.volume_low, result.volume_high), (29.0, 32.0))
        self.assertEqual(result.archetype, "intermediate")
        self.assertEqual(result.confidence, "high")

    def test_low_fitness_and_age_add_volume(self):
        base = recommend_archetype_volume(height_cm=None, weight_kg=75, skill="intermediate", fitness="average", sessions_per_week=2)
        adjusted = recommend_archetype_volume(height_cm=None, weight_kg=75, skill="intermediate", fitness="low", sessions_per_week=0.5, age=55)
        self.assertGreater(adjusted.volume_low, base.volume_low)
        self.assertGreater(adjusted.volume_high, base.volume_high)


if __name__ == "__main__":
    unittest.main()
