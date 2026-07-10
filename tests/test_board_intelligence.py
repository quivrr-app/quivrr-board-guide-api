import unittest

from app.board_intelligence import board_intelligence_baseline, find_board_record, load_board_records


class BoardIntelligenceTests(unittest.TestCase):
    def test_baseline_counts_match_slice_2_audit(self):
        baseline = board_intelligence_baseline()
        self.assertEqual(baseline["canonical_board_profiles"], 573)
        self.assertEqual(baseline["graph_eligible_models"], 513)
        self.assertEqual(baseline["unclassified_board_intelligence_records"], 308)
        self.assertEqual(baseline["invalid_relationship_references"], 0)

    def test_normalized_records_load_for_graph_eligible_models(self):
        rows = load_board_records()
        self.assertEqual(len(rows), 513)
        self.assertTrue(all(row.brand and row.model for row in rows))

    def test_known_board_contains_merged_identity_and_sizes(self):
        phantom = find_board_record("Pyzel", "Phantom")
        self.assertIsNotNone(phantom)
        self.assertTrue(phantom.graph_eligible)
        self.assertTrue(phantom.sizes)
        self.assertTrue(phantom.description)


if __name__ == "__main__":
    unittest.main()
