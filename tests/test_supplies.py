import unittest
from unittest.mock import patch

import printer_state
from snmp_client import SnmpValue


class FakeClient:
    def __init__(self, *_args, **_kwargs):
        self.scalars = {
            printer_state.OID_NAME: SnmpValue(printer_state.OID_NAME, 0x04, "HP M176n"),
            printer_state.OID_UPTIME: SnmpValue(printer_state.OID_UPTIME, 0x43, 12000),
            printer_state.OID_MODEL: SnmpValue(printer_state.OID_MODEL, 0x04, "HP Color LaserJet Pro MFP M176n"),
            printer_state.OID_PRINTER_STATUS: SnmpValue(printer_state.OID_PRINTER_STATUS, 0x02, 3),
            printer_state.OID_ERROR_FLAGS: SnmpValue(printer_state.OID_ERROR_FLAGS, 0x04, "\x00"),
        }
        self.rows = {
            printer_state.SUPPLY_COLUMNS["type"]: [("1", 3), ("2", 3), ("3", 3), ("4", 3), ("5", 9)],
            printer_state.SUPPLY_COLUMNS["description"]: [("1", "CF350A"), ("2", "CF351A"), ("3", "CF353A"), ("4", "CF352A"), ("5", "CE314A")],
            printer_state.SUPPLY_COLUMNS["unit"]: [(str(i), 19) for i in range(1, 6)],
            printer_state.SUPPLY_COLUMNS["maximum"]: [(str(i), 100) for i in range(1, 6)],
            printer_state.SUPPLY_COLUMNS["level"]: [(str(i), 80 - (i - 1) * 10) for i in range(1, 6)],
            printer_state.SUPPLY_COLUMNS["color_index"]: [(str(i), i) for i in range(1, 6)],
            printer_state.COLORANT_DESC_BASE: [("1", "black"), ("2", "cyan"), ("3", "magenta"), ("4", "yellow"), ("5", "drum")],
        }

    def get_many(self, _oids):
        return self.scalars

    def walk(self, base):
        return [SnmpValue(f"{base}.{index}", 0x02 if isinstance(value, int) else 0x04, value) for index, value in self.rows.get(base, [])]


class PartialClient(FakeClient):
    def get_many(self, oids):
        if oids == [printer_state.OID_MODEL]:
            from snmp_client import SnmpError

            raise SnmpError("SNMP error-status=2")
        return {oid: self.scalars[oid] for oid in oids if oid in self.scalars}

    def walk(self, base):
        if base == printer_state.SUPPLIES_BASE + ".5.1":
            from snmp_client import SnmpError

            raise SnmpError("SNMP error-status=2")
        return super().walk(base)


class SupplyTests(unittest.TestCase):
    def test_dynamic_supply_mapping(self):
        config = {"ip": "192.168.1.20", "snmp_community": "ro", "snmp_port": 161, "snmp_timeout": 1, "snmp_retries": 1}
        with patch.object(printer_state, "SnmpV1Client", FakeClient):
            result = printer_state.collect(config)
        self.assertTrue(result.online)
        self.assertNotEqual(result.state, "error")
        self.assertEqual(set(result.supplies), {"preto", "ciano", "magenta", "amarelo", "cilindro_imagem"})
        self.assertEqual(result.supplies["preto"]["percent"], 80)
        self.assertEqual(result.uptime_seconds, 120)

    def test_unsupported_optional_oid_does_not_abort_collection(self):
        config = {"ip": "192.168.1.20", "snmp_community": "ro", "snmp_port": 161, "snmp_timeout": 1, "snmp_retries": 1}
        with patch.object(printer_state, "SnmpV1Client", PartialClient):
            result = printer_state.collect(config)
        self.assertTrue(result.online)
        self.assertIsNone(result.model)
        self.assertIn("preto", result.supplies)


if __name__ == "__main__":
    unittest.main()
