import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from service import MonitorService
from settings import SettingsError, SettingsStore


class SettingsAndScheduleTests(unittest.TestCase):
    def test_public_settings_only_expose_user_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SettingsStore(Path(directory) / "config.json")
            store.save(
                {
                    "printer_name": "HP da recepção",
                    "ip": "192.168.1.20",
                    "snmp_community": "public",
                    "tasmota_entity": "switch.sonoff_impressora",
                    "tasmota_off_time": "03:15",
                }
            )
            public = store.public()
            self.assertEqual(
                set(public),
                {"printer_name", "ip", "snmp_community", "tasmota_entity", "tasmota_off_time"},
            )
            self.assertEqual(public["snmp_community"], {"configured": True})
            self.assertEqual(public["tasmota_off_time"], "03:15")

    def test_invalid_tasmota_values_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SettingsStore(Path(directory) / "config.json")
            with self.assertRaises(SettingsError):
                store.save({"tasmota_entity": "sonoff sem domínio"})
            with self.assertRaises(SettingsError):
                store.save({"tasmota_off_time": "25:99"})

    def test_tasmota_schedule_runs_once_per_day_and_entity(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SettingsStore(Path(directory) / "config.json")
            now = dt.datetime.now()
            store.save({"tasmota_entity": "switch.sonoff_impressora", "tasmota_off_time": now.strftime("%H:%M")})
            service = MonitorService(store)
            with patch("service.turn_off", return_value=(True, "Comando OFF enviado.")) as turn_off:
                service._check_tasmota_schedule()
                service._check_tasmota_schedule()
            turn_off.assert_called_once_with("switch.sonoff_impressora")


if __name__ == "__main__":
    unittest.main()
