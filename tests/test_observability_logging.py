import io
import json
import unittest
from contextlib import redirect_stdout

from app.structured_logging import emit_event


class BodhiObservabilityLoggingTests(unittest.TestCase):
    def test_bodhi_logger_redacts_user_message_text(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            emit_event(
                "bodhi_request_received",
                "bodhi_api",
                region="EU",
                status="success",
                message="show me the best board",
                page_context="product page",
            )
        payload = json.loads(buffer.getvalue().strip())
        self.assertEqual(payload["message"], "[REDACTED]")
        self.assertEqual(payload["page_context"], "[REDACTED]")


if __name__ == "__main__":
    unittest.main()
