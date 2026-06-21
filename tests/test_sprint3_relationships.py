import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import main
from app.board_relationship_graph import find_relationship_board, relationship_suggestions
from app.inventory_client import quivrr_search_url
from app.models import SuggestedBoard
from app.profile_engine import extract_profile


class Sprint3RelationshipTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)

    def post(self, message, conversation=None, region=None):
        return self.client.post("/api/board-guide/chat", json={
            "message": message, "conversation": conversation or [], "region": region,
        }).json()

    def test_hypto_more_performance_uses_curated_progression_and_volume_anchor(self):
        data = self.post("I ride a 29L Hypto and want more performance")
        self.assertEqual(data["intent"], "relationship_request")
        self.assertEqual(data["profile"]["current_volume_litres"], 29)
        self.assertIn("Pyzel Phantom", data["reply"])
        self.assertIn("JS Industries Xero Gravity", data["reply"])
        profile = extract_profile("I ride a 29L Hypto and want more performance")
        rows = relationship_suggestions(find_relationship_board("Haydenshapes", "Hypto Krypto"), "morePerformanceBoards", profile=profile)
        self.assertIn("28-30.5L", rows[0].suggested_size)

    def test_seaside_more_performance_prefers_controlled_fish_progression(self):
        data = self.post("What is like Seaside but more performance?")
        self.assertIn("Lost RNF 96", data["reply"])
        self.assertIn("JS Industries Black Baron", data["reply"])

    def test_phantom_easier_routes_to_forgiving_relationship(self):
        data = self.post("What is easier than a Phantom for average beach breaks?")
        self.assertEqual(data["intent"], "relationship_request")
        self.assertIn("Haydenshapes Hypto Krypto", data["reply"])

    def test_forgiving_followup_keeps_original_source_board(self):
        prior = [{"role": "user", "content": "I ride a 29L Hypto and want more performance in Australia"}]
        with patch.object(main, "enrich_suggestions_with_inventory", return_value=[]):
            data = self.post("Actually, more forgiving", prior, "AU")
        self.assertIn("Hypto Krypto", data["reply"])
        self.assertIn("Rare Bird", data["reply"])

    def test_stock_followup_checks_relationship_recommendations_not_source(self):
        prior = [{"role": "user", "content": "I ride a 29L Hypto and want more performance in Australia"}]

        def available(rows, _profile):
            return [row.model_copy(update={"available_count": 1, "region": "AU"}) for row in rows]

        with patch.object(main, "enrich_suggestions_with_inventory", side_effect=available):
            data = self.post("Yes, check the stock levels", prior, "AU")
        names = {row["model"] for row in data["suggested_boards"]}
        self.assertIn("Phantom", names)
        self.assertNotIn("Hypto Krypto", names)

    def test_fresh_fish_search_resets_relationship_topic(self):
        prior = [{"role": "user", "content": "I ride a 29L Hypto and want more performance"}]
        data = self.post("Show me fish boards for points in Australia", prior, "AU")
        self.assertNotEqual(data["intent"], "relationship_request")

    def test_eu_quivrr_link_cannot_leak_to_australia(self):
        board = SuggestedBoard(brand="Pyzel", model="Phantom", category="Daily Driver", confidence=.9, why_it_fits="test")
        url = quivrr_search_url(board, "EU")
        self.assertIn("quivrr.app/europe", url)
        self.assertIn("region=EU", url)
        self.assertNotIn("/australia", url)


if __name__ == "__main__":
    unittest.main()
