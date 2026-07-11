import unittest
from unittest.mock import Mock, patch

from app.authenticated_profile import load_authenticated_profile_context


class AuthenticatedProfileTests(unittest.TestCase):
    @patch("app.authenticated_profile.requests.get")
    def test_valid_profile_response_maps_to_rider_profile(self, requests_get):
        response = Mock()
        response.ok = True
        response.status_code = 200
        response.json.return_value = {
            "user": {"userId": "user-123", "displayName": "Nathan Dunn", "homeRegion": "ID"},
            "profile": {
                "weightKg": 78,
                "ability": "Advanced",
                "preferredBrands": ["JS Industries", "Album"],
                "currentBoard": "JS Monsta",
                "surfingGoal": "Performance progression",
                "homeBreak": "Canggu",
                "surfFrequency": "Weekly",
            },
        }
        requests_get.return_value = response

        context = load_authenticated_profile_context("Bearer token-123", correlation_id="corr-1")

        self.assertTrue(context.authenticated)
        self.assertTrue(context.profile_loaded)
        self.assertEqual(context.user_id, "user-123")
        self.assertEqual(context.profile.display_name, "Nathan Dunn")
        self.assertEqual(context.profile.region, "ID")
        self.assertEqual(context.profile.preferred_brands, ["JS Industries", "Album"])
        self.assertEqual(context.profile.surf_frequency_per_week, 1.0)

    @patch("app.authenticated_profile.requests.get")
    def test_unauthorised_profile_response_falls_back_without_profile(self, requests_get):
        response = Mock()
        response.ok = False
        response.status_code = 401
        requests_get.return_value = response

        context = load_authenticated_profile_context("Bearer token-123")

        self.assertFalse(context.authenticated)
        self.assertFalse(context.profile_loaded)
        self.assertTrue(context.invalid_token)
        self.assertIsNone(context.profile)


if __name__ == "__main__":
    unittest.main()
