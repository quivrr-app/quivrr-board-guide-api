import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import main
from app.conversation_flow import public_recommendations
from app.inventory_client import enrich_suggestions_with_inventory
from app.intent_router import classify_intent
from app.models import RiderProfile, SuggestedBoard


def offer(*, sponsored=False, price=1199.0, region="AU", construction="PU"):
    return {
        "offerId": "retailer:1",
        "canonicalModelId": 100,
        "canonicalBoardSizeId": 200,
        "brand": "Pyzel",
        "model": "Phantom",
        "construction": construction,
        "length": "5'10",
        "volumeLitres": 29.1,
        "retailerId": 10,
        "retailerName": "Test Surf Shop",
        "region": region,
        "currency": "AUD",
        "observedPrice": price,
        "stockStatus": "In Stock",
        "inStock": True,
        "productUrl": "https://shop.example/phantom",
        "sourceType": "retailer",
        "observedTimestamp": "2026-07-16T00:00:00Z",
        "matchQuality": "exact_model_and_size",
        "matchLabel": "Exact model and size match",
        "sponsored": sponsored,
        "sponsorCampaignId": "campaign-1" if sponsored else None,
        "sponsorDisclosure": "Promoted by Test Surf Shop" if sponsored else None,
    }


class RetailerOfferIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)
        self.board = SuggestedBoard(
            brand="Pyzel", model="Phantom", category="Daily Driver", confidence=0.9,
            why_it_fits="A balanced daily driver.", board_model_id=100,
        )

    def test_inventory_enrichment_carries_governed_offers_after_board_selection(self):
        payload = {
            "regionCode": "AU",
            "directManufacturerMatches": [],
            "exactRetailerMatches": [{
                "retailerInventoryId": 1, "productUrl": "https://shop.example/phantom",
                "stockStatus": "In Stock", "priceAmount": 1199, "priceCurrency": "AUD",
            }],
            "closeRetailerMatches": [],
            "offerIntelligence": {"offers": [offer()]},
        }

        def get_json(path):
            if path.startswith("/api/constructions/"):
                return [{"construction": "PU"}]
            if path.startswith("/api/sizes/"):
                return [{"boardSizeId": 200, "label": "5'10 | 29.1L", "volumeLitres": 29.1, "construction": "PU"}]
            if path.startswith("/api/search?"):
                return payload
            raise AssertionError(path)

        profile = RiderProfile(region="AU", target_volume_litres=29.0)
        result = enrich_suggestions_with_inventory([self.board], profile, get_json=get_json)[0]
        self.assertEqual(len(result.offers), 1)
        self.assertEqual(result.offers[0].currency, "AUD")
        self.assertEqual(result.offers[0].observed_price, 1199)

    def test_sponsorship_never_changes_board_recommendation_order(self):
        first = self.board.model_copy(update={"offers": [offer(sponsored=True)]})
        second = self.board.model_copy(update={
            "brand": "JS Industries", "model": "Xero Gravity", "confidence": 0.8,
            "offers": [offer(sponsored=False, price=900)],
        })
        cards = public_recommendations([first, second])
        self.assertEqual([card.model for card in cards], ["Phantom", "Xero Gravity"])
        self.assertTrue(cards[0].offers[0].sponsored)
        self.assertFalse(cards[1].offers[0].sponsored)

    def test_price_and_sponsorship_language_routes_to_availability(self):
        self.assertEqual(classify_intent("Which Phantom is the lowest observed Australian price?").intent, "AVAILABILITY")
        self.assertEqual(classify_intent("Does sponsorship affect your recommendation?").intent, "AVAILABILITY")

    @patch("main.is_azure_openai_configured", return_value=False)
    def test_sponsorship_explanation_is_transparent(self, _azure):
        response = self.client.post("/api/board-guide/chat", json={
            "message": "Does sponsorship affect your recommendation?", "region": "AU",
        })
        self.assertEqual(response.status_code, 200)
        reply = response.json()["reply"]
        self.assertIn("does not change Bodhi's board suitability", reply)
        self.assertIn("always labelled", reply)


if __name__ == "__main__":
    unittest.main()
