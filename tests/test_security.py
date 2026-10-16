import unittest
from pathlib import Path


class SecurityTests(unittest.TestCase):
    def test_reset_write_is_narrowly_scoped(self):
        source = Path(__file__).resolve().parents[1] / "tecnohead_hp" / "app" / "snmp_client.py"
        text = source.read_text(encoding="utf-8")
        self.assertIn("PRT_GENERAL_RESET_OID", text)
        self.assertIn("POWER_CYCLE_RESET_VALUE = 4", text)
        self.assertIn("def power_cycle_reset", text)
        self.assertNotIn("resetToNVRAM", text)
        self.assertNotIn("resetToFactoryDefaults", text)
        self.assertNotIn("def set", text.lower())

    def test_no_functional_remote_command_entities(self):
        config = (Path(__file__).resolve().parents[1] / "tecnohead_hp" / "config.yaml").read_text(encoding="utf-8")
        self.assertNotIn("button", config.lower())
        self.assertIn("ingress: true", config)


if __name__ == "__main__":
    unittest.main()
