import json
import unittest

from app.board_taxonomy import allows_category, find_taxonomy, load_taxonomy
from scripts import generate_board_taxonomy_v2 as generator


class BoardTaxonomyV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        generator.main()
        cls.rows = load_taxonomy()

    def test_approved_dataset_and_christenson_supplement_are_complete(self):
        self.assertEqual(len(self.rows), 431)
        self.assertEqual(len({row["canonical_key"] for row in self.rows}), 431)
        self.assertEqual(len({row["canonical_model_id"] for row in self.rows}), 431)
        self.assertEqual(len({row["brand"] for row in self.rows}), 17)

    def test_christenson_has_exactly_fourteen_canonical_models(self):
        expected = {
            "Acid Phish", "Cafe Racer", "Carrera", "Easy Wind", "Fish", "Flat Tracker V2",
            "Lane Splitter", "Lane Splitter Swallow", "Long Phish II", "OP2", "OP3", "OP4",
            "Osprey", "The Wolverine",
        }
        actual = {row["model"] for row in self.rows if row["brand"] == "Christenson"}
        self.assertEqual(actual, expected)

    def test_aliases_resolve_to_one_canonical_identity(self):
        cases = {
            "Cafe Racer 2.0": ("Cafe Racer", "8135"),
            "Flat Tracker 2.0": ("Flat Tracker V2", "8139"),
            "Wolverine": ("The Wolverine", "8148"),
            "op2": ("OP2", "8143"),
            "Op4": ("OP4", "8145"),
        }
        for alias, expected in cases.items():
            with self.subTest(alias=alias):
                row = find_taxonomy("Christenson", alias)
                self.assertEqual((row["model"], row["canonical_model_id"]), expected)

    def test_strict_categories_use_governed_inclusion_and_exclusion(self):
        fish = find_taxonomy("Christenson", "Fish")
        acid = find_taxonomy("Christenson", "Acid Phish")
        carrera = find_taxonomy("Christenson", "Carrera")
        op2 = find_taxonomy("Christenson", "OP2")
        osprey = find_taxonomy("Christenson", "Osprey")
        self.assertTrue(allows_category(fish, "fish"))
        self.assertTrue(allows_category(acid, "fish"))
        self.assertFalse(allows_category(carrera, "fish"))
        self.assertFalse(allows_category(op2, "fish"))
        self.assertFalse(allows_category(osprey, "fish"))
        self.assertTrue(allows_category(carrera, "step_up"))
        self.assertTrue(allows_category(osprey, "performance_mid_length"))

    def test_no_lane_is_both_included_and_excluded(self):
        for row in self.rows:
            with self.subTest(board=row["canonical_key"]):
                included = set(row["recommendation_lanes"])
                excluded = set(row["excluded_lanes"])
                self.assertFalse(included & excluded)

    def test_representative_christenson_comparisons_keep_distinct_design_intent(self):
        pairs = (
            ("Fish", "Carrera", "traditional_fish", "step_up"),
            ("Lane Splitter", "Acid Phish", "performance_twin", "performance_fish"),
            ("OP4", "Carrera", "performance_shortboard", "step_up"),
            ("Osprey", "Long Phish II", "performance_mid_length", "performance_mid_length"),
            ("Easy Wind", "Cafe Racer", "hybrid_shortboard", "performance_daily_driver"),
        )
        for left_name, right_name, left_category, right_category in pairs:
            with self.subTest(left=left_name, right=right_name):
                left = find_taxonomy("Christenson", left_name)
                right = find_taxonomy("Christenson", right_name)
                self.assertEqual(left["primary_category"], left_category)
                self.assertEqual(right["primary_category"], right_category)
                self.assertNotEqual(left["canonical_model_id"], right["canonical_model_id"])
                self.assertNotEqual(
                    (left["primary_category"], left["secondary_categories"], left["recommendation_lanes"]),
                    (right["primary_category"], right["secondary_categories"], right["recommendation_lanes"]),
                )

    def test_generation_is_deterministic(self):
        before = generator.OUTPUT.read_bytes()
        generator.main()
        self.assertEqual(before, generator.OUTPUT.read_bytes())


if __name__ == "__main__":
    unittest.main()
