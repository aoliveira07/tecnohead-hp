"""Small SNMPv1 client with a single, tightly-scoped reset operation.

Discovery and monitoring use only GET and GETNEXT. The only write supported by
this module is the explicitly named ``power_cycle_reset`` operation for the
Printer-MIB ``prtGeneralReset`` object. It is deliberately not a generic SET
API: the OID and value are fixed, and the caller must perform its own
capability and state checks before invoking it.
"""

from __future__ import annotations

import socket
import struct
from dataclasses import dataclass
from typing import Any, Iterable


class SnmpError(RuntimeError):
    """An SNMP operation failed."""


class SnmpCommandError(SnmpError):
    """A one-shot command failed after it may have reached the device."""

    def __init__(self, message: str, *, command_sent: bool) -> None:
        super().__init__(message)
        self.command_sent = command_sent


PRT_GENERAL_RESET_OID = "1.3.6.1.2.1.43.5.1.1.3.1"
POWER_CYCLE_RESET_VALUE = 4


@dataclass(frozen=True)
class SnmpValue:
    oid: str
    tag: int
    value: Any

    @property
    def is_missing(self) -> bool:
        return self.tag in {0x80, 0x81, 0x82, 0x05}


def _encode_length(length: int) -> bytes:
    if length < 0x80:
        return bytes([length])
    raw = length.to_bytes((length.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(raw)]) + raw


def _tlv(tag: int, payload: bytes) -> bytes:
    return bytes([tag]) + _encode_length(len(payload)) + payload


def _encode_integer(value: int) -> bytes:
    if value == 0:
        return b"\x00"
    width = max(1, (value.bit_length() + 8) // 8)
    raw = value.to_bytes(width, "big", signed=True)
    while len(raw) > 1 and ((raw[0] == 0 and not raw[1] & 0x80) or (raw[0] == 0xFF and raw[1] & 0x80)):
        raw = raw[1:]
    return raw


def _encode_oid(oid: str) -> bytes:
    parts = [int(part) for part in oid.strip(".").split(".")]
    if len(parts) < 2 or parts[0] not in (0, 1, 2) or parts[1] < 0:
        raise ValueError(f"OID inválido: {oid}")
    encoded = bytes([parts[0] * 40 + parts[1]])
    for part in parts[2:]:
        if part < 0:
            raise ValueError(f"OID inválido: {oid}")
        chunks = [part & 0x7F]
        part >>= 7
        while part:
            chunks.append(0x80 | (part & 0x7F))
            part >>= 7
        encoded += bytes(reversed(chunks))
    return _tlv(0x06, encoded)


def _decode_oid(payload: bytes) -> str:
    if not payload:
        raise SnmpError("OID vazio na resposta SNMP")
    first = payload[0]
    if first < 40:
        values = [0, first]
    elif first < 80:
        values = [1, first - 40]
    else:
        values = [2, first - 80]
    value = 0
    for byte in payload[1:]:
        value = (value << 7) | (byte & 0x7F)
        if not byte & 0x80:
            values.append(value)
            value = 0
    if payload[-1] & 0x80:
        raise SnmpError("OID truncado na resposta SNMP")
    return ".".join(str(item) for item in values)


def _read_tlv(data: bytes, offset: int) -> tuple[int, bytes, int]:
    if offset + 2 > len(data):
        raise SnmpError("TLV SNMP truncado")
    tag = data[offset]
    first_length = data[offset + 1]
    offset += 2
    if first_length & 0x80:
        count = first_length & 0x7F
        if count == 0 or offset + count > len(data):
            raise SnmpError("Comprimento SNMP inválido")
        length = int.from_bytes(data[offset : offset + count], "big")
        offset += count
    else:
        length = first_length
    end = offset + length
    if end > len(data):
        raise SnmpError("Conteúdo SNMP truncado")
    return tag, data[offset:end], end


def _decode_value(tag: int, payload: bytes) -> Any:
    if tag == 0x05:
        return None
    if tag == 0x04:
        return payload.decode("utf-8", errors="replace")
    if tag == 0x06:
        return _decode_oid(payload)
    if tag == 0x40 and len(payload) == 4:
        return socket.inet_ntoa(payload)
    if tag in {0x41, 0x42, 0x43, 0x46}:
        return int.from_bytes(payload, "big", signed=False)
    if tag in {0x02, 0x80, 0x81, 0x82}:
        return int.from_bytes(payload, "big", signed=(tag == 0x02)) if payload else None
    return payload.hex()


def _parse_response(data: bytes) -> tuple[int, list[SnmpValue]]:
    tag, message, end = _read_tlv(data, 0)
    if tag != 0x30 or end != len(data):
        raise SnmpError("Resposta SNMP não é uma sequência válida")
    offset = 0
    version_tag, _, offset = _read_tlv(message, offset)
    if version_tag != 0x02:
        raise SnmpError("Versão SNMP ausente")
    community_tag, _, offset = _read_tlv(message, offset)
    if community_tag != 0x04:
        raise SnmpError("Comunidade SNMP ausente")
    pdu_tag, pdu, offset = _read_tlv(message, offset)
    if pdu_tag != 0xA2:
        raise SnmpError(f"PDU SNMP inesperado: 0x{pdu_tag:02x}")
    pdu_offset = 0
    _, _, pdu_offset = _read_tlv(pdu, pdu_offset)  # request-id
    error_tag, error_payload, pdu_offset = _read_tlv(pdu, pdu_offset)
    if error_tag != 0x02:
        raise SnmpError("error-status SNMP ausente")
    error_status = int.from_bytes(error_payload, "big", signed=True)
    _, _, pdu_offset = _read_tlv(pdu, pdu_offset)  # error-index
    list_tag, varbinds, pdu_offset = _read_tlv(pdu, pdu_offset)
    if list_tag != 0x30:
        raise SnmpError("Lista de varbinds SNMP ausente")

    values: list[SnmpValue] = []
    var_offset = 0
    while var_offset < len(varbinds):
        bind_tag, bind, var_offset = _read_tlv(varbinds, var_offset)
        if bind_tag != 0x30:
            raise SnmpError("Varbind SNMP inválido")
        bind_offset = 0
        oid_tag, oid_payload, bind_offset = _read_tlv(bind, bind_offset)
        value_tag, value_payload, bind_offset = _read_tlv(bind, bind_offset)
        if oid_tag != 0x06:
            raise SnmpError("OID ausente em varbind SNMP")
        oid = _decode_oid(oid_payload)
        values.append(SnmpValue(oid, value_tag, _decode_value(value_tag, value_payload)))
    return error_status, values


class SnmpV1Client:
    """Minimal SNMPv1 client with defensive timeouts and retry limits."""

    def __init__(self, host: str, community: str, port: int = 161, timeout: float = 3.0, retries: int = 1) -> None:
        self.host = host
        self.community = community
        self.port = port
        self.timeout = max(0.1, min(float(timeout), 30.0))
        self.retries = max(1, min(int(retries), 3))
        self._request_id = 1000

    def _exchange(self, packet: bytes, *, attempts: int | None = None) -> list[SnmpValue]:
        last_error: Exception | None = None
        for _ in range(max(1, attempts if attempts is not None else self.retries)):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                    sock.settimeout(self.timeout)
                    sock.sendto(packet, (self.host, self.port))
                    response, _ = sock.recvfrom(65535)
                error_status, values = _parse_response(response)
                if error_status:
                    raise SnmpError(f"SNMP error-status={error_status}")
                return values
            except (OSError, SnmpError) as exc:
                last_error = exc
        raise SnmpError(f"Falha SNMPv1 em {self.host}: {last_error}")

    def _request(self, pdu_tag: int, oids: Iterable[str]) -> list[SnmpValue]:
        oid_list = list(oids)
        if not oid_list:
            return []
        self._request_id = (self._request_id + 1) & 0x7FFFFFFF
        varbinds = b"".join(_tlv(0x30, _encode_oid(oid) + _tlv(0x05, b"")) for oid in oid_list)
        pdu = _tlv(
            pdu_tag,
            _tlv(0x02, _encode_integer(self._request_id))
            + _tlv(0x02, _encode_integer(0))
            + _tlv(0x02, _encode_integer(0))
            + _tlv(0x30, varbinds),
        )
        packet = _tlv(0x30, _tlv(0x02, _encode_integer(0)) + _tlv(0x04, self.community.encode()) + pdu)
        return self._exchange(packet)

    def _send_reset_value(self, reset_value: int) -> list[SnmpValue]:
        """Send exactly one fixed Printer-MIB reset request.

        This method has no retry path by design. A lost response can mean the
        printer rebooted successfully, so repeating the request could trigger
        a second reboot. The service layer performs read-only verification and
        reports an inconclusive result when necessary.
        """

        if reset_value not in {4, 5, 6}:
            raise ValueError("Valor de reset não permitido.")
        self._request_id = (self._request_id + 1) & 0x7FFFFFFF
        value = _tlv(0x02, _encode_integer(reset_value))
        varbind = _tlv(0x30, _encode_oid(PRT_GENERAL_RESET_OID) + value)
        pdu = _tlv(
            0xA3,
            _tlv(0x02, _encode_integer(self._request_id))
            + _tlv(0x02, _encode_integer(0))
            + _tlv(0x02, _encode_integer(0))
            + _tlv(0x30, varbind),
        )
        packet = _tlv(0x30, _tlv(0x02, _encode_integer(0)) + _tlv(0x04, self.community.encode()) + pdu)

        command_sent = False
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.settimeout(self.timeout)
                sock.sendto(packet, (self.host, self.port))
                command_sent = True
                response, _ = sock.recvfrom(65535)
        except OSError as exc:
            raise SnmpCommandError(f"Falha ao enviar/receber o reboot SNMP: {type(exc).__name__}.", command_sent=command_sent) from exc

        try:
            error_status, values = _parse_response(response)
        except SnmpError as exc:
            raise SnmpCommandError(str(exc), command_sent=command_sent) from exc
        if error_status:
            raise SnmpCommandError(f"SNMP error-status={error_status}", command_sent=command_sent)
        return values

    def power_cycle_reset(self) -> list[SnmpValue]:
        """Send exactly one ``powerCycleReset(4)`` request."""

        return self._send_reset_value(POWER_CYCLE_RESET_VALUE)

    def reset_to_nvram(self) -> list[SnmpValue]:
        """Send exactly one ``resetToNVRAM(5)`` request."""

        return self._send_reset_value(5)

    def reset_to_factory_defaults(self) -> list[SnmpValue]:
        """Send exactly one ``resetToFactoryDefaults(6)`` request."""

        return self._send_reset_value(6)

    def get(self, oid: str) -> SnmpValue | None:
        values = self._request(0xA0, [oid])
        return values[0] if values else None

    def get_many(self, oids: Iterable[str]) -> dict[str, SnmpValue]:
        values = self._request(0xA0, list(oids))
        return {value.oid: value for value in values}

    def walk(self, base_oid: str, max_rows: int = 128) -> list[SnmpValue]:
        base = base_oid.strip(".")
        current = base
        result: list[SnmpValue] = []
        seen: set[str] = set()
        for _ in range(max_rows):
            values = self._request(0xA1, [current])
            if not values:
                break
            value = values[0]
            if value.oid == current or not value.oid.startswith(base + ".") or value.oid in seen or value.is_missing:
                break
            seen.add(value.oid)
            result.append(value)
            current = value.oid
        return result


def ticks_to_seconds(value: Any) -> float | None:
    """Convert TimeTicks (hundredths of a second) without overflowing."""

    if not isinstance(value, int) or value < 0:
        return None
    return value / 100.0
