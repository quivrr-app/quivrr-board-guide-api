import unittest

from app.azure_openai_client import build_bodhi_request_payload


class AzureOpenAIRequestAuditTests(unittest.TestCase):
    def test_current_request_has_auditable_prompt_and_no_tool_or_history_contract(self):
        payload = build_bodhi_request_payload(
            deployment="bodhi-chat",
            user_content="Region: AU\nUser message: Why do fish feel fast?",
            timeout_seconds=20,
        )

        self.assertEqual(payload["model"], "bodhi-chat")
        self.assertEqual(len(payload["messages"]), 2)
        self.assertEqual(payload["messages"][1]["content"], "Region: AU\nUser message: Why do fish feel fast?")
        self.assertNotIn("tools", payload)
        self.assertNotIn("tool_choice", payload)
        self.assertNotIn("response_format", payload)

