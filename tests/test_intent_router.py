import unittest

from app.intent_router import classify_intent, route_intent


class IntentRouterContractTests(unittest.TestCase):
    def test_classify_intent_preserves_legacy_route_string(self):
        message = "Compare Pyzel Phantom and JS Monsta"
        result = classify_intent(message)
        self.assertEqual(result.intent, route_intent(message))
        self.assertTrue(result.needs_board_pair)

    def test_exact_location_sets_region_hint(self):
        result = classify_intent("Where can I buy a JS Monsta 5'11 in Europe?")
        self.assertEqual(result.intent, "exact_board_location_request")
        self.assertTrue(result.needs_region)

    def test_general_fit_request_falls_back_to_surfer_fit(self):
        result = classify_intent("I'm 75kg and need help choosing a board")
        self.assertEqual(result.intent, "surfer_fit_request")


if __name__ == "__main__":
    unittest.main()
