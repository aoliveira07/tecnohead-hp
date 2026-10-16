import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from service import MonitorService
from settings import SettingsStore
from snmp_client import POWER_CYCLE_RESET_VALUE, PRT_GENERAL_RESET_OID, SnmpError, SnmpValue


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

    def test_forced_path_skips_probe_but_uses_only_power_cycle_reset(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SettingsStore(Path(directory) / "config.json")
            store.save(
                {
                    "ip": "192.168.0.55",
                    "snmp_write_community": "write",
                    "allow_reset_test": True,
                }
            )
            service = MonitorService(store)
            service._state.update({"configured": True, "online": True, "state": "idle", "state_label": "Ociosa", "uptime_seconds": 120.0})
            fake_client = MagicMock()
            fake_client.power_cycle_reset.return_value = [SnmpValue(PRT_GENERAL_RESET_OID, 0x02, POWER_CYCLE_RESET_VALUE)]
            with patch("service.SnmpV1Client", return_value=fake_client) as client_factory:
                result = service.test_reboot(force=True)

        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "sent")
        self.assertTrue(result["command_sent"])
        client_factory.assert_called_once()
        fake_client.get.assert_not_called()
        fake_client.power_cycle_reset.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
