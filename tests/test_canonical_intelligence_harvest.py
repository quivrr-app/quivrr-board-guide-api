import json
import unittest

from scripts import harvest_canonical_board_intelligence as harvest


class CanonicalIntelligenceHarvestTests(unittest.TestCase):
    def test_sharp_eye_structured_scale_extraction(self):
        description = (
            "Overview Performance Range - TEST Model. Recommended for intermediate to expert surfers. "
            "Ideal Wave Size: 2-6ft. Wave Type: beach break and reef break. Model Outline Performance Range. "
            "A performance outline with sensitive low rails, medium entry rocker and full exit rocker. Fin Setup: Thruster."
        )
        category, source = harvest.extract_manufacturer_category("Sharp Eye", "Test", description)
        self.assertEqual((category, source), ("Performance Range", "manufacturer_product_description"))
        self.assertEqual(harvest.map_manufacturer_category("Sharp Eye", category, description)[0], "performance_shortboard")
        self.assertEqual(harvest.extract_wave_range(description)[:2], (2.0, 6.0))
        self.assertEqual(harvest.extract_wave_types(description)[0], ["beach_break", "reef_break"])
        self.assertEqual(harvest.extract_abilities(description)[:2], ("intermediate", "expert"))
        self.assertIn("low rails", harvest.design_value(description, "railType").lower())
        self.assertIn("entry rocker", harvest.design_value(description, "entryRocker").lower())
        self.assertIn("exit rocker", harvest.design_value(description, "exitRocker").lower())

    def test_manufacturer_category_mappings(self):
        cases = [
            ("Pyzel", "Daily Drivers", "", "daily_driver"),
            ("Pyzel", "High Performance", "", "high_performance"),
            ("Pyzel", "Funformance", "Made for small weak waves", "groveller"),
            ("Lost", "Something Fishy", "", "fish"),
            ("Lost", "Recreational Vehicles", "", "hybrid"),
            ("Lost", "Step Ups", "", "step_up"),
            ("JS Industries", "Daily Series", "", "daily_driver"),
            ("JS Industries", "Performer Series", "", "performance_shortboard"),
            ("JS Industries", "Charger Series", "", "step_up"),
            ("JS Industries", "Youth Series", "", "youth"),
            ("JS Industries", "Softboards", "", "softboard"),
        ]
        for brand, manufacturer_category, description, expected in cases:
            with self.subTest(brand=brand, category=manufacturer_category):
                primary, _, source, confidence = harvest.map_manufacturer_category(brand, manufacturer_category, description)
                self.assertEqual(primary, expected)
                self.assertEqual(source, "deterministic_category_mapping")
                self.assertEqual(confidence, "medium")

    def test_category_index_preserves_manufacturer_page_provenance(self):
        index = {
            ("js industries", "big horse"): [
                {"manufacturerCategory": "Charger Series", "sourceUrl": "https://jsindustries.com/collections/charger-series-1"},
                {"manufacturerCategory": "Performer Series", "sourceUrl": "https://jsindustries.com/collections/performer-series"},
            ]
        }
        category, source_url, categories = harvest.indexed_category("JS Industries", "Big Horse", index)
        self.assertEqual(category, "Charger Series")
        self.assertEqual(categories, ["Charger Series", "Performer Series"])
        self.assertTrue(source_url.startswith("https://jsindustries.com/"))

    def test_generic_descriptions_are_rejected_without_overwriting_good_copy(self):
        groups = {
            ("a", "one"): [{"brand": "A", "model": "One", "description": "Generic manufacturer description " * 5}],
            ("a", "two"): [{"brand": "A", "model": "Two", "description": "Generic manufacturer description " * 5}],
            ("a", "three"): [{"brand": "A", "model": "Three", "description": "Generic manufacturer description " * 5}],
            ("a", "good"): [{"brand": "A", "model": "Good", "description": "A model-specific manufacturer description with enough detail to remain intact. " * 2}],
        }
        descriptions = harvest.description_candidates(groups)
        self.assertNotIn(("a", "one"), descriptions)
        self.assertEqual(descriptions[("a", "good")], groups[("a", "good")][0]["description"])

    def test_retailer_url_cannot_become_canonical_source(self):
        rows = [{
            "brand": "JS Industries", "model": "Monsta", "description_source_type": "manufacturer",
            "description_source_url": "https://58surf.com/eng/example", "official_product_url": "https://58surf.com/eng/example",
        }]
        self.assertEqual(harvest.trusted_source(rows), (None, None))

    def test_applied_output_has_global_schema_and_field_confidence(self):
        self.assertEqual(harvest.main(["--apply"]), 0)
        payload = json.loads(harvest.OUTPUT_PATH.read_text(encoding="utf-8"))
        self.assertEqual(payload["schemaVersion"], "canonical_board_intelligence_v1")
        self.assertEqual(len(payload["profiles"]), 518)
        profile = next(row for row in payload["profiles"] if row["identity"]["brand"] == "Sharp Eye" and row["identity"]["model"] == "#77")
        self.assertEqual(profile["description"]["descriptionConfidence"], "high")
        self.assertEqual(profile["category"]["manufacturerCategoryConfidence"], "high")
        self.assertIn(profile["category"]["categoryConfidence"], {"medium", "high"})
        self.assertNotIn("regionCode", json.dumps(profile))


if __name__ == "__main__":
    unittest.main()
