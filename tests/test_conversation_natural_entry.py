import unittest

from fastapi.testclient import TestClient

import main


class NaturalConversationEntryTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)

    def ask(self, message: str):
        response = self.client.post("/api/board-guide/chat", json={"message": message})
        response.raise_for_status()
        return response.json()

    def test_greeting_is_conversational_not_form(self):
        body = self.ask("Hey")
        self.assertEqual(body["intent"], "greeting_request")
        self.assertIn("Hey mate", body["reply"])
        self.assertNotIn("Tell me your weight", body["reply"])

    def test_best_shortboard_answers_before_intake(self):
        body = self.ask("what's the best shortboard?")
        self.assertEqual(body["intent"], "expert_board_question")
        self.assertIn("There is no single best shortboard", body["reply"])
        self.assertIn("Pyzel Phantom", body["reply"])
        self.assertIn("JS Xero Gravity", body["reply"])
        self.assertEqual(body["recommendations"], [])

    def test_best_fish_answers_as_expert_question(self):
        body = self.ask("what is the best fish?")
        self.assertEqual(body["intent"], "expert_board_question")
        self.assertIn("Album Lightbender", body["reply"])
        self.assertIn("Lost RNF 96", body["reply"])
        self.assertEqual(body["recommendations"], [])


if __name__ == "__main__":
    unittest.main()
