import unittest

from capabilities import command_allowed
from mqtt_commands import handle_command


class CommandTests(unittest.TestCase):
    def test_reboot_is_blocked_without_homologation(self):
        allowed, reason = command_allowed("restart", enabled=True, capability_validated=False, printer_state="idle", cooldown_ok=True)
        self.assertFalse(allowed)
        self.assertIn("homologada", reason)

    def test_dangerous_state_is_blocked(self):
        result = handle_command("restart", config={"allow_remote_control": True}, printer_state="printing", capability_validated=True, cooldown_ok=True)
        self.assertFalse(result["accepted"])


if __name__ == "__main__":
    unittest.main()
