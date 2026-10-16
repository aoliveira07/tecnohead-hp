import unittest
from unittest.mock import patch

from mqtt_discovery import BASE_TOPIC, DEVICE_ID, MqttPublisher, _supervisor_mqtt, build_discovery_payloads


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

    @patch.dict("os.environ", {"SUPERVISOR_TOKEN": "token"}, clear=False)
    @patch("mqtt_discovery.urlopen")
    def test_supervisor_mqtt_unwraps_data(self, urlopen):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return b'{"data":{"host":"core-mosquitto","port":1883,"ssl":false,"username":"ha","password":"secret"}}'

        urlopen.return_value = Response()
        self.assertEqual(
            _supervisor_mqtt(),
            {"host": "core-mosquitto", "port": 1883, "ssl": False, "username": "ha", "password": "secret"},
        )

    def test_mqtt_v2_reason_code_is_handled(self):
        publisher = MqttPublisher(lambda: {})

        class ReasonCode:
            value = 0

            def __int__(self):
                raise TypeError("paho v2 reason codes are not directly int-convertible")

        publisher._on_connect(None, None, None, ReasonCode())
        self.assertTrue(publisher.connected)


def json_text(value):
    import json
    return json.dumps(value)


if __name__ == "__main__":
    unittest.main()
