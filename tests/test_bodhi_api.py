import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import main


class BodhiApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)

    @patch("main.is_azure_openai_configured", return_value=False)
    @patch("main.enrich_suggestions_with_inventory", side_effect=lambda rows, _profile: rows)
    def test_28_litre_request_asks_one_useful_question(self, _inventory, _azure):
        response = self.client.post("/api/board-guide/chat", json={
            "message": "I want a new shortboard around 28 litres", "region": "EU",
        })
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["profile"]["target_volume_litres"], 28)
        self.assertIn("weight", body["reply"].lower())

    @patch("main.is_azure_openai_configured", return_value=False)
    @patch("main.enrich_suggestions_with_inventory", side_effect=lambda rows, _profile: rows)
    def test_opening_greeting(self, _inventory, _azure):
        response = self.client.post("/api/board-guide/chat", json={"message": ""})
        self.assertIn("live board availability across Quivrr", response.json()["reply"])


if __name__ == "__main__":
    unittest.main()
