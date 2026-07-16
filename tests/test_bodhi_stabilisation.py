import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import main
from app.conversation_flow import public_recommendations
from app.inventory_client import enrich_suggestions_with_inventory
from app.models import RiderProfile, SuggestedBoard


class BodhiStabilisationTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)

    def ask(self, message, **extra):
        response = self.client.post("/api/board-guide/chat", json={"message": message, **extra})
        response.raise_for_status()
        return response.json()

    def test_three_board_comparison_mentions_every_board(self):
        body = self.ask(
            "Compare Happy Everyday, Xero Gravity and Phantom for a 75kg surfer in average Australian beach breaks."
        )
        self.assertEqual(body["intent"], "comparison_request")
        for model in ("Happy Everyday", "Xero Gravity", "Phantom"):
            self.assertIn(model, body["reply"])
        self.assertNotIn("weight?", body["reply"].lower())
        self.assertEqual(body["recommendations"], [])

    def test_comparison_follow_up_retains_boards(self):
        body = self.ask(
            "I already told you my weight and region. Australia and I’m 75kg. So I’m looking around 28 litres.",
            conversation=[{
                "role": "user",
                "content": "Compare Happy Everyday, Xero Gravity and Phantom for a 75kg surfer in average Australian beach breaks.",
            }],
        )
        self.assertEqual(body["intent"], "comparison_request")
        for model in ("Happy Everyday", "Xero Gravity", "Phantom"):
            self.assertIn(model, body["reply"])
        for wrong in ("Hypto Krypto", "Churro 2", "Rare Bird"):
            self.assertNotIn(wrong, body["reply"])
        self.assertIn("around 28L", body["reply"])

    @patch("main.enrich_suggestions_with_inventory", side_effect=lambda rows, profile: [
        row.model_copy(update={"available_count": 1, "retailer_count": 1, "region": profile.region})
        for row in rows
    ])
    def test_advanced_performance_daily_driver_prioritises_correct_lane(self, _inventory):
        body = self.ask(
            "I’m 75kg, advanced, surfing Australian beach breaks 2-6ft. I want a performance daily driver, not a hybrid."
        )
        first = [row["model"].replace("-", " ").lower() for row in body["recommendations"][:5]]
        expected = {"phantom", "xero gravity", "happy everyday", "inferno 72", "rad ripper", "cafe racer"}
        self.assertTrue(set(first[:3]).issubset(expected))
        self.assertTrue({"phantom", "xero gravity"}.issubset(first[:3]))
        self.assertNotEqual(first[0], "hypto krypto")
        self.assertFalse(any(model in first[:3] for model in ["hypto krypto", "churro 2", "rare bird evo"]))
        self.assertTrue(all(row["region"] == "AU" for row in body["recommendations"]))

    @patch("main.enrich_suggestions_with_inventory", side_effect=lambda rows, profile: [
        row.model_copy(update={"available_count": 1, "retailer_count": 1, "region": profile.region})
        for row in rows
    ])
    def test_monsta_pushback_explains_tradeoffs_and_checks_everyday_set(self, inventory):
        body = self.ask(
            "Monsta might be a bit aggressive for me. I’m looking more at an everyday board. Gravity or Happy Everyday.",
            region="AU",
            conversation=[{"role": "user", "content": "You suggested the JS Monsta for me."}],
        )
        self.assertIn("sharper, more demanding", body["reply"])
        self.assertIn("friendlier everyday shortboard", body["reply"])
        self.assertIn("Pyzel Phantom", body["reply"])
        checked = {row.model.replace("-", " ").lower() for row in inventory.call_args.args[0]}
        self.assertEqual(checked, {"xero gravity", "happy everyday", "phantom"})
        self.assertTrue(all(row["region"] == "AU" for row in body["recommendations"]))

    @patch("main.enrich_suggestions_with_inventory", side_effect=lambda rows, profile: [
        row.model_copy(update={"available_count": 1, "retailer_count": 1, "region": profile.region})
        for row in rows
    ])
    def test_stock_confirmation_checks_only_active_comparison(self, inventory):
        body = self.ask(
            "yes, check the stock levels",
            conversation=[{
                "role": "user",
                "content": "Compare Happy Everyday, Xero Gravity and Phantom for a 75kg surfer in Australian beach breaks.",
            }],
        )
        self.assertEqual(body["intent"], "comparison_request")
        checked = {row.model.replace("-", " ").lower() for row in inventory.call_args.args[0]}
        self.assertEqual(checked, {"happy everyday", "xero gravity", "phantom"})
        self.assertEqual(len(body["recommendations"]), 3)

    @patch("main.enrich_suggestions_with_inventory", side_effect=lambda rows, profile: [
        row.model_copy(update={"available_count": 1, "retailer_count": 1, "region": profile.region})
        for row in rows
    ])
    def test_fresh_daily_driver_request_clears_fish_comparison(self, _inventory):
        body = self.ask(
            "show me three good daily drivers for Australia",
            conversation=[{
                "role": "user",
                "content": "Compare Seaside, RNF 96 and Lightbender for point breaks.",
            }],
        )
        self.assertEqual(body["intent"], "board_search_request")
        self.assertTrue(body["recommendations"])
        self.assertEqual(len(body["recommendations"]), 3)
        self.assertNotIn("Lightbender", body["reply"])
        self.assertNotIn("Seaside", body["reply"])
        self.assertNotIn("RNF 96", body["reply"])
        top = [row["model"].replace("-", " ").lower() for row in body["recommendations"][:3]]
        self.assertFalse(any(model in top for model in ["hypto krypto", "churro 2", "rare bird evo"]))

    def test_fish_twin_comparison_uses_surf_shop_semantics(self):
        body = self.ask("Compare Seaside, RNF 96 and Lightbender for point breaks.")
        self.assertIn("Seaside is the easiest and cruisier", body["reply"])
        self.assertIn("RNF 96 is the more performance-led fish", body["reply"])
        self.assertIn("Lightbender is the refined performance twin / point-break twin", body["reply"])
        self.assertIn("easier speed, more performance, or cleaner point-break lines", body["reply"])

    def test_inventory_preserves_source_url_and_builds_quivrr_cta(self):
        def get_json(path):
            if path == "/api/brands":
                return [{"brandId": 1, "brandName": "Pyzel"}]
            if path == "/api/models/1":
                return [{"modelId": 2, "modelName": "Phantom"}]
            if path == "/api/constructions/2":
                return [{"construction": "PU"}]
            if path == "/api/sizes/2/PU":
                return [{"boardSizeId": 12345, "label": "5'10 | 28L", "volumeLitres": 28, "construction": "PU"}]
            if path == "/api/search?boardSizeId=12345&region=EU":
                return {"regionCode": "EU", "directManufacturerMatches": [], "exactRetailerMatches": [{
                    "retailerInventoryId": 8, "productUrl": "https://retailer.example/phantom", "stockStatus": "in_stock",
                }], "closeRetailerMatches": []}
            raise AssertionError(path)

        board = SuggestedBoard(brand="Pyzel", model="Phantom", category="Performance Daily Driver",
                               confidence=.95, why_it_fits="fit")
        enriched = enrich_suggestions_with_inventory([board], RiderProfile(region="EU", target_volume_litres=28), get_json)[0]
        public = public_recommendations([enriched])[0]
        self.assertTrue(enriched.quivrr_search_url.startswith("https://quivrr.app/europe?"))
        self.assertIn("boardSizeId=12345", enriched.quivrr_search_url)
        self.assertEqual(public.example_product_url, "https://quivrr.app/europe/?brand=Pyzel&model=Phantom")
        self.assertEqual(public.search_url, "https://quivrr.app/europe/?brand=Pyzel&model=Phantom")
        self.assertNotIn("boardSizeId", public.example_product_url)
        self.assertEqual(public.source_product_url, "https://retailer.example/phantom")
        self.assertEqual(public.availability_status, "retailer_stock")
        self.assertTrue(public.exact_size_stock)
        self.assertTrue(public.availability_checked)
        self.assertEqual(public.inventory_match_count, 1)
        self.assertEqual(public.manufacturer_match_count, 0)
        self.assertEqual(public.retailer_match_count, 1)
        self.assertEqual(public.region_code, "EU")

    def test_us_deep_link_uses_united_states_path(self):
        board = SuggestedBoard(
            brand="Pyzel",
            model="Ghost",
            category="Performance Daily Driver",
            confidence=0.91,
            why_it_fits="fit",
        )
        enriched = enrich_suggestions_with_inventory([board], RiderProfile(region="US"), lambda path: {
            "/api/brands": [{"brandId": 1, "brandName": "Pyzel"}],
            "/api/models/1": [{"modelId": 2, "modelName": "Ghost"}],
            "/api/constructions/2": [{"construction": "PU"}],
            "/api/sizes/2/PU": [{"boardSizeId": 999, "label": "6'0 | 30L", "volumeLitres": 30, "construction": "PU"}],
            "/api/search?boardSizeId=999&region=US": {"regionCode": "US", "directManufacturerMatches": [], "exactRetailerMatches": [], "closeRetailerMatches": []},
        }[path])[0]
        self.assertTrue(enriched.quivrr_search_url.startswith("https://quivrr.app/united-states?"))
        self.assertEqual(enriched.availability_status, "not_found")


if __name__ == "__main__":
    unittest.main()
