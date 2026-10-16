import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from service import MonitorService
from settings import SettingsStore
from snmp_client import POWER_CYCLE_RESET_VALUE, PRT_GENERAL_RESET_OID, SnmpError, SnmpValue


class RebootFlowTests(unittest.TestCase):
    def test_reset_lab_lists_standard_values_and_hp_private_root(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SettingsStore(Path(directory) / "config.json")
            lab = MonitorService(store).reset_lab()

        self.assertEqual(lab["oid"], PRT_GENERAL_RESET_OID)
        self.assertEqual([item["value"] for item in lab["catalog"]["values"]], [3, 4, 5, 6])
        self.assertEqual([item["value"] for item in lab["catalog"]["candidates"]], [4, 5, 6])
        self.assertEqual(lab["catalog"]["hp_private_enterprise_root"], "1.3.6.1.4.1.11")

    def test_direct_candidate_sends_without_probe_state_or_cooldown(self):
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
            fake_client = MagicMock()
            fake_client.reset_to_factory_defaults.return_value = [SnmpValue(PRT_GENERAL_RESET_OID, 0x02, 6)]
            with patch("service.SnmpV1Client", return_value=fake_client) as client_factory:
                result = service.send_reset_candidate("factory")

        self.assertTrue(result["command_sent"])
        self.assertEqual(result["status"], "sent")
        client_factory.assert_called_once_with("192.168.0.55", "write", 161, 3.0, retries=1)
        fake_client.reset_to_factory_defaults.assert_called_once_with()

    def test_direct_all_sends_each_catalog_value_without_post_wait(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SettingsStore(Path(directory) / "config.json")
            store.save({"ip": "192.168.0.55", "snmp_write_community": "write", "allow_reset_test": True})
            service = MonitorService(store)
            fake_client = MagicMock()
            fake_client.power_cycle_reset.return_value = [SnmpValue(PRT_GENERAL_RESET_OID, 0x02, 4)]
            fake_client.reset_to_nvram.return_value = [SnmpValue(PRT_GENERAL_RESET_OID, 0x02, 5)]
            fake_client.reset_to_factory_defaults.return_value = [SnmpValue(PRT_GENERAL_RESET_OID, 0x02, 6)]
            with patch("service.SnmpV1Client", return_value=fake_client):
                result = service.send_all_reset_candidates()

        self.assertEqual(result["status"], "batch_sent")
        self.assertEqual(len(result["results"]), 3)
        self.assertEqual(sum(item["command_sent"] for item in result["results"]), 3)
        fake_client.power_cycle_reset.assert_called_once_with()
        fake_client.reset_to_nvram.assert_called_once_with()
        fake_client.reset_to_factory_defaults.assert_called_once_with()

    def test_reset_lab_probe_is_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SettingsStore(Path(directory) / "config.json")
            store.save({"ip": "192.168.0.55", "snmp_community": "read"})
            service = MonitorService(store)
            fake_client = MagicMock()
            fake_client.get.return_value = SnmpValue(PRT_GENERAL_RESET_OID, 0x02, 3)
            fake_client.walk.return_value = [SnmpValue("1.3.6.1.2.1.43.5.1.1.3.1", 0x02, 3)]
            with patch("service.SnmpV1Client", return_value=fake_client):
                result = service.probe_reset_lab()

        self.assertTrue(result["ok"])
        fake_client.get.assert_called_once_with(PRT_GENERAL_RESET_OID)
        self.assertEqual(fake_client.walk.call_count, 2)
        fake_client.power_cycle_reset.assert_not_called()
        fake_client.reset_to_nvram.assert_not_called()
        fake_client.reset_to_factory_defaults.assert_not_called()

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

    def test_destructive_modes_require_exact_phrase_and_use_fixed_method(self):
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
            service._state.update({"configured": True, "online": True, "state": "idle", "state_label": "Ociosa"})
            fake_client = MagicMock()
            fake_client.reset_to_factory_defaults.return_value = [SnmpValue(PRT_GENERAL_RESET_OID, 0x02, 6)]
            with patch("service.SnmpV1Client", return_value=fake_client):
                blocked = service.test_reset("factory", "wrong")
                result = service.test_reset("factory", "RESET_FACTORY_DEFAULTS")

        self.assertFalse(blocked["command_sent"])
        self.assertEqual(result["status"], "sent")
        fake_client.reset_to_factory_defaults.assert_called_once_with()
        fake_client.reset_to_nvram.assert_not_called()


if __name__ == "__main__":
    unittest.main()
