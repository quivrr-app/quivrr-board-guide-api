import unittest

import requests

from app.inventory_client import enrich_suggestions_with_inventory
from app.model_recommendation_engine import find_board_description
from app.models import RiderProfile, SuggestedBoard
from app.profile_engine import build_recommendation, extract_profile
from app.rider_fit import recommend_rider_fit
from scripts.scrape_manufacturer_board_descriptions import extract_description


class RiderFitTests(unittest.TestCase):
    def test_75kg_intermediate_weekly_surfer(self):
        result = recommend_rider_fit(RiderProfile(
            weight_kg=75, ability="Intermediate", surf_frequency_per_week=1,
        ))
        self.assertEqual(result.volume_range_label, "29 to 33L")

    def test_75kg_advanced_frequent_surfer(self):
        result = recommend_rider_fit(RiderProfile(
            weight_kg=75, ability="Advanced", surf_frequency_per_week=4, fitness_level="High",
        ))
        self.assertEqual(result.volume_range_label, "26 to 29L")

    def test_low_fitness_adjustment(self):
        normal = recommend_rider_fit(RiderProfile(weight_kg=75, ability="Intermediate"))
        low = recommend_rider_fit(RiderProfile(weight_kg=75, ability="Intermediate", fitness_level="Low"))
        self.assertGreater(low.volume_low, normal.volume_low)
        self.assertTrue(any("fitness" in note for note in low.adjustment_factors))

    def test_small_weak_wave_adjustment(self):
        normal = recommend_rider_fit(RiderProfile(weight_kg=75, ability="Intermediate"))
        weak = recommend_rider_fit(RiderProfile(
            weight_kg=75, ability="Intermediate", wave_size="1-2ft", wave_type="Soft beach break",
        ))
        self.assertGreater(weak.volume_high, normal.volume_high)

    def test_daily_driver_recommendation(self):
        profile = extract_profile("75kg intermediate daily driver, once a week", "EU")
        recommendation = build_recommendation(profile)
        self.assertIn("Everyday", recommendation.board_category)
        self.assertEqual(recommendation.suggested_volume_range_litres, "29 to 33L")

    def test_performance_shortboard_recommendation(self):
        profile = extract_profile("75kg advanced, 4 times per week, more performance shortboard", "AU")
        recommendation = build_recommendation(profile)
        self.assertEqual(recommendation.board_category, "Performance shortboard")
        self.assertEqual(recommendation.suggested_volume_range_litres, "25 to 28L")


class InventoryTests(unittest.TestCase):
    def suggestion(self):
        return SuggestedBoard(
            brand="JS Industries", model="Monsta", category="Performance shortboard",
            confidence=0.9, why_it_fits="Target fit",
        )

    @staticmethod
    def fake_catalogue(path):
        if path == "/api/brands":
            return [{"brandId": 4, "brandName": "JS Industries"}]
        if path == "/api/models/4":
            return [{"modelId": 10, "modelName": "Monsta"}]
        if path == "/api/constructions/10":
            return [{"construction": "PU"}]
        if path == "/api/sizes/10/PU":
            return [{"boardSizeId": 100, "label": "5'11 | 28L", "volumeLitres": 28}]
        if path.startswith("/api/search?"):
            return {
                "regionCode": "AU",
                "directManufacturerMatches": [{"isAvailable": True, "productUrl": "https://au.example"}],
                "exactRetailerMatches": [], "closeRetailerMatches": [],
            }
        raise AssertionError(path)

    def test_region_filter_never_returns_au_for_eu(self):
        rows = enrich_suggestions_with_inventory(
            [self.suggestion()], RiderProfile(weight_kg=75, ability="Intermediate", region="EU"),
            get_json=self.fake_catalogue,
        )
        self.assertEqual(rows[0].available_count, 0)
        self.assertIsNone(rows[0].example_live_source_url)

    def test_no_hallucinated_stock_when_inventory_unavailable(self):
        def broken(_path):
            raise requests.ConnectionError("offline")
        rows = enrich_suggestions_with_inventory(
            [self.suggestion()], RiderProfile(weight_kg=75, ability="Intermediate", region="EU"),
            get_json=broken,
        )
        self.assertEqual(rows[0].available_count, 0)


class DescriptionTests(unittest.TestCase):
    def test_board_description_retrieval(self):
        row = find_board_description("Pyzel", "Ghost", [{
            "brand": "Pyzel", "model": "Ghost", "model_description": "Manufacturer description",
            "short_description": "Short", "source_url": "https://pyzel.example/ghost", "source_type": "manufacturer",
        }])
        self.assertEqual(row["description"], "Manufacturer description")
        self.assertEqual(row["sourceType"], "manufacturer")

    def test_missing_description_fallback(self):
        self.assertIsNone(find_board_description("Pyzel", "Ghost", [{"brand": "Pyzel", "model": "Ghost"}]))

    def test_manufacturer_html_description_extraction(self):
        page = '<script type="application/ld+json">{"@type":"Product","description":"A manufacturer model description with enough useful detail about rocker, rails, waves and intended surfers."}</script>'
        self.assertIn("manufacturer model description", extract_description(page))


if __name__ == "__main__":
    unittest.main()
