import unittest

from snmp_client import SnmpValue, _decode_oid, _encode_oid, _parse_response, _tlv


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


if __name__ == "__main__":
    unittest.main()
