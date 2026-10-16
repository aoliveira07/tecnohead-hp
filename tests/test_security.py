import unittest
from pathlib import Path


class SecurityTests(unittest.TestCase):
    def test_no_snmp_set_implementation(self):
        source = Path(__file__).resolve().parents[1] / "tecnohead_hp" / "app" / "snmp_client.py"
        self.assertNotIn("snmpset", source.read_text(encoding="utf-8").lower())
        self.assertNotIn("def set", source.read_text(encoding="utf-8").lower())

    def test_no_functional_remote_command_entities(self):
        config = (Path(__file__).resolve().parents[1] / "tecnohead_hp" / "config.yaml").read_text(encoding="utf-8")
        self.assertNotIn("button", config.lower())
        self.assertIn("ingress: true", config)


if __name__ == "__main__":
    unittest.main()
