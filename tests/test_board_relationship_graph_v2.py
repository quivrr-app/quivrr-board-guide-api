import hashlib
import json
import unittest

from app.board_relationship_graph import find_relationship_board, relationship_suggestions
from scripts import generate_board_relationship_graph as generator


class BoardRelationshipGraphV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        generator.main()
        cls.payload = json.loads(generator.OUTPUT_PATH.read_text(encoding="utf-8-sig"))

    def test_graph_covers_canonical_models_without_self_edges(self):
        self.assertEqual(len(self.payload["boards"]), 513)
        identities = {(row["brand"].lower(), row["model"].lower()) for row in self.payload["boards"]}
        for board in self.payload["boards"]:
            for relation, edges in board["relationships"].items():
                self.assertLessEqual(len(edges), 8)
                for edge in edges:
                    self.assertNotEqual((edge["brand"].lower(), edge["model"].lower()), (board["brand"].lower(), board["model"].lower()))
                    self.assertIn((edge["brand"].lower(), edge["model"].lower()), identities)
                    self.assertEqual(edge["relationshipType"], relation)
                    self.assertIn(edge["confidence"], {"high", "medium", "low"})

    def test_hypto_more_performance_includes_phantom(self):
        hypto = find_relationship_board("Haydenshapes", "Hypto Krypto")
        identities = {(row["brand"], row["model"]) for row in hypto["relationships"]["morePerformanceBoards"]}
        self.assertIn(("Pyzel", "Phantom"), identities)

    def test_rnf_relationships_include_fish_and_point_options(self):
        rnf = find_relationship_board("Lost", "RNF 96")
        similar = {(row["brand"], row["model"]) for row in rnf["relationships"]["similarBoards"]}
        points = {(row["brand"], row["model"]) for row in rnf["relationships"]["betterPointBreakBoards"]}
        self.assertIn(("Firewire", "Seaside"), similar)
        self.assertTrue({("Album", "Lightbender"), ("Christenson", "Ocean Racer")} <= points)

    def test_runtime_suggestions_preserve_relationship_evidence(self):
        hypto = find_relationship_board("Haydenshapes", "Hypto Krypto")
        rows = relationship_suggestions(hypto, "morePerformanceBoards")
        self.assertEqual(rows[0].model, "Phantom")
        self.assertEqual(rows[0].source, "quivrr_board_relationship_graph_v2")

    def test_generation_is_deterministic(self):
        before = hashlib.sha256(generator.OUTPUT_PATH.read_bytes()).hexdigest()
        generator.main()
        after = hashlib.sha256(generator.OUTPUT_PATH.read_bytes()).hexdigest()
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
