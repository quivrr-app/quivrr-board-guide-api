import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import main


class ActiveBoardInventoryTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)

    @patch("main.is_azure_openai_configured", return_value=False)
    @patch("main.model_availability")
    def test_pronoun_inventory_uses_the_active_canonical_board_and_exact_size(self, availability, _azure):
        availability.return_value = {
            "regionCode": "ID",
            "availableSizes": [{
                "boardSizeId": 901, "length": "5'3", "width": "20 1/2", "thickness": "2 7/16",
                "volumeLitres": 28.0, "construction": "PU", "finSetup": "Twin",
                "minimumPrice": 14500000, "currency": "IDR", "manufacturerAvailable": False,
                "retailerCount": 1, "offers": [{"sourceType": "retailer", "retailerName": "Indo Surf", "productUrl": "https://example.test/53"}],
            }],
        }
        response = self.client.post("/api/board-guide/chat", json={
            "message": "check if its available and in what sizes?",
            "region": "ID",
            "profile": {"region": "ID", "current_volume_litres": 28.6},
            "conversationState": {
                "lastIntent": "BOARD_RECOMMENDATION",
                "activeRegion": "ID",
                "activeBoard": {"brand": "Album", "model": "Plasmic", "boardModelId": 205, "canonicalKey": "album|plasmic"},
            },
        })
        self.assertEqual(response.status_code, 200)
        body = response.json()
        availability.assert_called_once_with(205, "ID")
        self.assertEqual(body["intent"], "active_board_inventory_request")
        self.assertIn("Album Plasmic", body["reply"])
        self.assertIn("IDR", body["reply"])
        self.assertEqual(body["conversationState"]["activeBoard"]["boardModelId"], 205)
        card = body["recommendations"][0]
        self.assertEqual(card["boardSizeId"], 901)
        self.assertIn("boardSizeId=901", card["searchUrl"])
        self.assertIn("autoSearch=1", card["searchUrl"])


if __name__ == "__main__":
    unittest.main()
