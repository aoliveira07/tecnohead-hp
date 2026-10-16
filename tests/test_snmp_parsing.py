import unittest
from unittest.mock import patch

from snmp_client import POWER_CYCLE_RESET_VALUE, PRT_GENERAL_RESET_OID, SnmpValue, SnmpV1Client, _decode_oid, _encode_oid, _parse_response, _tlv


class _FakeSocket:
    def __init__(self, response: bytes):
        self.response = response
        self.sent: list[tuple[bytes, tuple[str, int]]] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def settimeout(self, _timeout):
        return None

    def sendto(self, packet, address):
        self.sent.append((packet, address))

    def recvfrom(self, _size):
        return self.response, ("192.0.2.1", 161)


class SnmpParsingTests(unittest.TestCase):
    def test_oid_round_trip(self):
        encoded = _encode_oid("1.3.6.1.2.1.43.11.1.1.9.1.5")
        self.assertEqual(encoded[0], 0x06)
        length = encoded[1]
        self.assertEqual(_decode_oid(encoded[2 : 2 + length]), "1.3.6.1.2.1.43.11.1.1.9.1.5")

    def test_parse_response_with_timeticks_and_string(self):
        first_oid = _encode_oid("1.3.6.1.2.1.1.5.0") + _tlv(0x04, b"HP M176n")
        second_oid = _encode_oid("1.3.6.1.2.1.1.3.0") + _tlv(0x43, (12345).to_bytes(2, "big"))
        varbinds = _tlv(0x30, first_oid) + _tlv(0x30, second_oid)
        pdu = _tlv(0xA2, _tlv(0x02, b"\x01") + _tlv(0x02, b"\x00") + _tlv(0x02, b"\x00") + _tlv(0x30, varbinds))
        packet = _tlv(0x30, _tlv(0x02, b"\x00") + _tlv(0x04, b"ro") + pdu)
        error_status, values = _parse_response(packet)
        self.assertEqual(error_status, 0)
        self.assertEqual(values[0], SnmpValue("1.3.6.1.2.1.1.5.0", 0x04, "HP M176n"))
        self.assertEqual(values[1].value, 12345)

    def test_power_cycle_packet_is_fixed_to_value_four_and_sent_once(self):
        response_varbind = _tlv(0x30, _encode_oid(PRT_GENERAL_RESET_OID) + _tlv(0x02, bytes([POWER_CYCLE_RESET_VALUE])))
        response_pdu = _tlv(0xA2, _tlv(0x02, b"\x01") + _tlv(0x02, b"\x00") + _tlv(0x02, b"\x00") + _tlv(0x30, response_varbind))
        response = _tlv(0x30, _tlv(0x02, b"\x00") + _tlv(0x04, b"rw") + response_pdu)
        fake = _FakeSocket(response)
        with patch("snmp_client.socket.socket", return_value=fake):
            values = SnmpV1Client("192.0.2.10", "rw", retries=3).power_cycle_reset()
        self.assertEqual(len(fake.sent), 1)
        packet = fake.sent[0][0]
        self.assertIn(_encode_oid(PRT_GENERAL_RESET_OID) + _tlv(0x02, b"\x04"), packet)
        self.assertNotIn(_encode_oid(PRT_GENERAL_RESET_OID) + _tlv(0x02, b"\x05"), packet)
        self.assertEqual(values[0].value, POWER_CYCLE_RESET_VALUE)

    def test_nvram_and_factory_packets_use_fixed_values(self):
        for method, reset_value in (("reset_to_nvram", 5), ("reset_to_factory_defaults", 6)):
            with self.subTest(method=method):
                response_varbind = _tlv(0x30, _encode_oid(PRT_GENERAL_RESET_OID) + _tlv(0x02, bytes([reset_value])))
                response_pdu = _tlv(0xA2, _tlv(0x02, b"\x01") + _tlv(0x02, b"\x00") + _tlv(0x02, b"\x00") + _tlv(0x30, response_varbind))
                response = _tlv(0x30, _tlv(0x02, b"\x00") + _tlv(0x04, b"rw") + response_pdu)
                fake = _FakeSocket(response)
                with patch("snmp_client.socket.socket", return_value=fake):
                    values = getattr(SnmpV1Client("192.0.2.10", "rw"), method)()
                packet = fake.sent[0][0]
                self.assertIn(_encode_oid(PRT_GENERAL_RESET_OID) + _tlv(0x02, bytes([reset_value])), packet)
                self.assertEqual(values[0].value, reset_value)


if __name__ == "__main__":
    unittest.main()
