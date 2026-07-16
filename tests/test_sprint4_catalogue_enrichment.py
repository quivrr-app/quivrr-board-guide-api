import json
import unittest
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "app" / "knowledge" / "generated" / "canonical_board_profiles.json"
GENERATED = ROOT / "app" / "knowledge" / "generated" / "board_intelligence_generated.json"


def _clean(value: object) -> str:
    return " ".join(str(value or "").split())


class Sprint4CatalogueEnrichmentTests(unittest.TestCase):
    def test_priority_brands_have_full_description_coverage(self):
        rows = json.loads(CANONICAL.read_text(encoding="utf-8"))
        priority = {"Christenson", "Album", "JS Industries", "Pukas", "DMS Surfboards"}
        by_brand_model = defaultdict(dict)
        for row in rows:
            brand = row.get("brand")
            model = row.get("model")
            if brand not in priority or not model:
                continue
            by_brand_model[brand][model] = bool(_clean(row.get("description")))

        expected_models = {
            "Christenson": 36,
            "Album": 19,
            "JS Industries": 30,
            "Pukas": 13,
            "DMS Surfboards": 8,
        }
        for brand, expected_count in expected_models.items():
            with self.subTest(brand=brand):
                self.assertEqual(len(by_brand_model[brand]), expected_count)
                self.assertTrue(all(by_brand_model[brand].values()))

    def test_christenson_descriptions_do_not_leak_shopify_metadata(self):
        rows = json.loads(CANONICAL.read_text(encoding="utf-8"))
        tokens = [
            "Surfboard Model:",
            "Surfboard ID:",
            "Surfboard Model Type:",
            "Fins:",
            "Skip to main content",
            "About / Team / SURFBOARDS",
        ]
        christenson = [row for row in rows if row.get("brand") == "Christenson"]
        self.assertTrue(christenson)
        for row in christenson:
            description = _clean(row.get("description"))
            self.assertTrue(description)
            for token in tokens:
                self.assertNotIn(token.lower(), description.lower())

    def test_weak_intelligence_is_below_five_percent(self):
        boards = json.loads(GENERATED.read_text(encoding="utf-8-sig")).get("boards", [])
        weak = 0
        for board in boards:
            desc = _clean(board.get("model_description"))
            short = _clean(board.get("short_description"))
            summary = _clean(board.get("summary"))
            confidence = float(board.get("classificationConfidence") or 0)
            board_name = f"{board.get('brand')} {board.get('model')}".strip()
            is_weak = False
            if not desc and not short:
                is_weak = True
            if confidence <= 0.25:
                is_weak = True
            if summary in {board_name, f"{board_name}."}:
                is_weak = True
            if is_weak:
                weak += 1
        self.assertLess((weak / len(boards)) * 100, 5.0)


if __name__ == "__main__":
    unittest.main()
