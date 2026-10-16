import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from service import MonitorService
from settings import SettingsStore
from snmp_client import SnmpError


class RebootFlowTests(unittest.TestCase):
    def test_missing_reset_oid_never_reaches_write_path(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SettingsStore(Path(directory) / "config.json")
            store.save(
                {
                    "ip": "192.168.0.55",
                    "snmp_community": "read",
                    "snmp_write_community": "write",
                    "allow_reset_test": True,
                }
            )
            fake_client = MagicMock()
            fake_client.get.side_effect = SnmpError("SNMP error-status=2")
            with patch("service.SnmpV1Client", return_value=fake_client) as client_factory:
                result = MonitorService(store).test_reboot()

        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "unavailable")
        self.assertFalse(result["command_sent"])
        self.assertEqual(client_factory.call_count, 1)
        fake_client.power_cycle_reset.assert_not_called()


if __name__ == "__main__":
    unittest.main()
