import tempfile
import unittest
from pathlib import Path

from settings import SettingsError, SettingsStore


class FailureTests(unittest.TestCase):
    def test_empty_ip_is_allowed_for_first_install(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SettingsStore(Path(directory) / "config.json")
            value = store.save({"ip": ""})
            self.assertEqual(value["ip"], "")

    def test_public_ip_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SettingsStore(Path(directory) / "config.json")
            with self.assertRaises(SettingsError):
                store.save({"ip": "8.8.8.8"})

    def test_secret_is_not_returned(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SettingsStore(Path(directory) / "config.json")
            store.save({"snmp_community": "private-ro"})
            public = store.public()
            self.assertEqual(public["snmp_community"], {"configured": True})


if __name__ == "__main__":
    unittest.main()
