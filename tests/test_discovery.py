import unittest

from mqtt_discovery import BASE_TOPIC, DEVICE_ID, build_discovery_payloads


class DiscoveryTests(unittest.TestCase):
    def test_stable_device_and_no_ip_in_topics(self):
        state = {"configured": True, "online": True, "state": "idle", "state_label": "Ociosa", "collected_at": "2026-10-16T00:00:00+00:00", "uptime_seconds": 10, "supplies": {"preto": {"name": "Toner preto", "percent": 80, "source": "SNMP"}}}
        payloads = build_discovery_payloads(state)
        self.assertTrue(payloads)
        self.assertTrue(all(DEVICE_ID in topic for topic in payloads))
        self.assertTrue(all(BASE_TOPIC not in topic for topic in payloads))
        online = next(value for topic, value in payloads.items() if topic.endswith(f"{DEVICE_ID}_online/config"))
        self.assertEqual(online["device"]["identifiers"], [DEVICE_ID])
        self.assertNotIn("ip", json_text(payloads))

    def test_no_entities_before_configuration(self):
        self.assertEqual(build_discovery_payloads({"configured": False}), {})


def json_text(value):
    import json
    return json.dumps(value)


if __name__ == "__main__":
    unittest.main()
