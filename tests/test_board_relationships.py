import unittest

from app.board_relationship_graph import find_relationship_board, relationship_suggestions


class BoardRelationshipsTests(unittest.TestCase):
    def test_relationship_lookup_returns_controlled_alternatives(self):
        hypto = find_relationship_board("Haydenshapes", "Hypto Krypto")
        self.assertIsNotNone(hypto)

        rows = relationship_suggestions(hypto, "morePerformanceBoards")

        self.assertTrue(rows)
        self.assertEqual(rows[0].source, "quivrr_board_relationship_graph_v3")
        self.assertTrue(any(row.model == "Phantom" for row in rows))


if __name__ == "__main__":
    unittest.main()
