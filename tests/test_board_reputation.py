import unittest

from fastapi.testclient import TestClient

import main
from app.board_reputation import compact_reputation, get_reputation


class BoardReputationTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)

    def test_reputation_loads_iconic_boards(self):
        self.assertIsNotNone(get_reputation("Album", "Lightbender"))
        self.assertIn("point", compact_reputation("Album", "Lightbender").lower())
        self.assertIn("hybrid", compact_reputation("Haydenshapes", "Hypto Krypto").lower())

    def test_relationship_reply_uses_surf_shop_language(self):
        body = self.client.post(
            "/api/board-guide/chat",
            json={"message": "What is more performance than a Hypto Krypto?"},
        ).json()
        self.assertEqual(body["intent"], "relationship_request")
        self.assertIn("If you like the Haydenshapes Hypto Krypto", body["reply"])
        self.assertIn("Pyzel Phantom", body["reply"])
        self.assertIn("surf-shop", body["reply"])

    def test_point_break_fish_reply_uses_reputation_context(self):
        body = self.client.post(
            "/api/board-guide/chat",
            json={"message": "What is like a Lost RNF 96 but better for point breaks?"},
        ).json()
        self.assertEqual(body["intent"], "relationship_request")
        self.assertIn("point breaks", body["reply"].lower())
        self.assertIn("Album Lightbender", body["reply"])
        self.assertIn("down-the-line", body["reply"])


if __name__ == "__main__":
    unittest.main()
