import json
import unittest
from unittest.mock import patch

from home_assistant import turn_off


class HomeAssistantTests(unittest.TestCase):
    @patch.dict("os.environ", {"SUPERVISOR_TOKEN": "token"}, clear=False)
    @patch("home_assistant.urlopen")
    def test_turn_off_uses_core_api_and_entity(self, urlopen):
        class Response:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        urlopen.return_value = Response()
        ok, message = turn_off("switch.sonoff_impressora")
        self.assertTrue(ok)
        self.assertIn("switch.sonoff_impressora", message)
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "http://supervisor/core/api/services/homeassistant/turn_off")
        self.assertEqual(json.loads(request.data), {"entity_id": "switch.sonoff_impressora"})
        self.assertIn("Bearer token", request.get_header("Authorization"))

    @patch.dict("os.environ", {}, clear=True)
    @patch("home_assistant.urlopen")
    def test_turn_off_without_supervisor_token_does_not_call_network(self, urlopen):
        ok, message = turn_off("switch.sonoff_impressora")
        self.assertFalse(ok)
        self.assertIn("SUPERVISOR_TOKEN", message)
        urlopen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
