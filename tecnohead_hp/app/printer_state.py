"""SNMP collection and normalization for the HP M176n."""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from typing import Any

from snmp_client import SnmpError, SnmpValue, SnmpV1Client, ticks_to_seconds


OID_NAME = "1.3.6.1.2.1.1.5.0"
OID_UPTIME = "1.3.6.1.2.1.1.3.0"
OID_MODEL = "1.3.6.1.2.1.25.3.2.1.3.1"
OID_GENERAL_STATUS = "1.3.6.1.2.1.25.3.2.1.5.1"
OID_PRINTER_STATUS = "1.3.6.1.2.1.25.3.5.1.1.1"
OID_ERROR_FLAGS = "1.3.6.1.2.1.25.3.5.1.2.1"
SUPPLIES_BASE = "1.3.6.1.2.1.43.11.1.1"
COLORANT_DESC_BASE = "1.3.6.1.2.1.43.12.1.1.4.1"

SUPPLY_COLUMNS = {
    "type": f"{SUPPLIES_BASE}.5.1",
    "description": f"{SUPPLIES_BASE}.6.1",
    "unit": f"{SUPPLIES_BASE}.7.1",
    "maximum": f"{SUPPLIES_BASE}.8.1",
    "level": f"{SUPPLIES_BASE}.9.1",
    "color_index": f"{SUPPLIES_BASE}.3.1",
}

PRINTER_STATES = {
    1: ("outro", "Outro"),
    2: ("unknown", "Desconhecida"),
    3: ("idle", "Ociosa"),
    4: ("printing", "Imprimindo"),
    5: ("warmup", "Aquecendo"),
}

SUPPLY_NAMES = {
    "preto": "Toner preto",
    "ciano": "Toner ciano",
    "magenta": "Toner magenta",
    "amarelo": "Toner amarelo",
    "cilindro_imagem": "Cilindro de imagem",
}


@dataclass
class CollectionResult:
    online: bool = False
    state: str = "unknown"
    state_label: str = "Desconhecida"
    name: str | None = None
    model: str | None = None
    uptime_seconds: float | None = None
    error_flags: int | None = None
    error: str | None = None
    supplies: dict[str, dict[str, Any]] = field(default_factory=dict)
    sources: dict[str, str] = field(default_factory=dict)
    collected_at: str | None = None

    def public(self) -> dict[str, Any]:
        return {
            "online": self.online,
            "state": self.state,
            "state_label": self.state_label,
            "name": self.name,
            "model": self.model,
            "uptime_seconds": self.uptime_seconds,
            "error_flags": self.error_flags,
            "error": self.error,
            "supplies": self.supplies,
            "sources": self.sources,
            "collected_at": self.collected_at,
        }


def _last_index(oid: str) -> str:
    return oid.rsplit(".", 1)[-1]


def _value(values: dict[str, SnmpValue], oid: str) -> Any:
    found = values.get(oid)
    if found is None or found.is_missing:
        return None
    return found.value


def _normalize_description(description: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", description.lower()).strip()


def _classify_supply(description: str, supply_type: Any, colorant: str) -> str | None:
    text = _normalize_description(f"{description} {colorant}")
    code = description.upper().replace(" ", "")
    if "CE314A" in code or "DRUM" in text or "CILIND" in text or supply_type == 9:
        return "cilindro_imagem"
    if "CF350A" in code or "BLACK" in text or "PRETO" in text or "BLACK" in colorant.upper():
        return "preto"
    if "CF351A" in code or "CYAN" in text or "CIANO" in text or "CYAN" in colorant.upper():
        return "ciano"
    if "CF353A" in code or "MAGENTA" in text or "MAGENTA" in colorant.upper():
        return "magenta"
    if "CF352A" in code or "YELLOW" in text or "AMARELO" in text or "YELLOW" in colorant.upper():
        return "amarelo"
    if supply_type == 3 and any(token in text for token in ("black", "cyan", "magenta", "yellow", "preto", "ciano", "amarelo")):
        return next((key for key in SUPPLY_NAMES if key in text), None)
    return None


def _percent(level: Any, maximum: Any, unit: Any) -> float | None:
    if not isinstance(level, int) or level < 0 or level in {-1, -2, -3, -4}:
        return None
    if unit == 19 and maximum == 100:
        return float(max(0, min(100, level)))
    if isinstance(maximum, int) and maximum > 0 and 0 <= level <= maximum:
        return round((level / maximum) * 100, 1)
    return None


def _normalize_error_flags(value: Any) -> Any:
    """Normalize HP's zero-filled OCTET STRING error flag response."""

    if isinstance(value, (bytes, bytearray)):
        return 0 if not any(value) else int.from_bytes(value, "big")
    if isinstance(value, str) and value and not any(ord(char) for char in value):
        return 0
    return value


def _safe_get_many(client: SnmpV1Client, oids: list[str]) -> dict[str, SnmpValue]:
    """Read scalar OIDs independently so one unsupported OID cannot abort all data."""

    values: dict[str, SnmpValue] = {}
    for oid in oids:
        try:
            values.update(client.get_many([oid]))
        except SnmpError:
            continue
    return values


def _safe_walk(client: SnmpV1Client, base_oid: str) -> list[SnmpValue]:
    """Treat an unsupported optional table as unavailable, not as a total failure."""

    try:
        return client.walk(base_oid)
    except SnmpError:
        return []


def collect(config: dict[str, Any]) -> CollectionResult:
    result = CollectionResult(collected_at=dt.datetime.now(dt.timezone.utc).isoformat())
    client = None
    if config.get("snmp_community"):
        client = SnmpV1Client(
            config["ip"],
            config["snmp_community"],
            port=config["snmp_port"],
            timeout=config["snmp_timeout"],
            retries=config["snmp_retries"],
        )
    try:
        if client is None:
            raise SnmpError("Comunidade SNMPv1 não configurada.")
        scalar_oids = [OID_NAME, OID_UPTIME, OID_MODEL, OID_GENERAL_STATUS, OID_PRINTER_STATUS, OID_ERROR_FLAGS]
        scalars = _safe_get_many(client, scalar_oids)
        if not scalars:
            raise SnmpError("SNMPv1 não retornou dados de estado.")
        result.name = _value(scalars, OID_NAME)
        result.model = _value(scalars, OID_MODEL)
        result.uptime_seconds = ticks_to_seconds(_value(scalars, OID_UPTIME))
        result.error_flags = _normalize_error_flags(_value(scalars, OID_ERROR_FLAGS))
        status = _value(scalars, OID_PRINTER_STATUS)
        if isinstance(status, int):
            result.state, result.state_label = PRINTER_STATES.get(status, ("unknown", f"Código {status}"))
        if result.error_flags not in (None, 0):
            result.state = "error"
            result.state_label = "Erro"
        result.sources.update({"name": "SNMP", "model": "SNMP", "state": "SNMP", "uptime": "SNMP", "errors": "SNMP"})

        colorants = {_last_index(item.oid): str(item.value) for item in _safe_walk(client, COLORANT_DESC_BASE)}
        columns: dict[str, dict[str, SnmpValue]] = {}
        for key, base in SUPPLY_COLUMNS.items():
            for item in _safe_walk(client, base):
                columns.setdefault(_last_index(item.oid), {})[key] = item
        for index, row in columns.items():
            description = str(row.get("description").value if row.get("description") else "")
            kind = row.get("type").value if row.get("type") else None
            colorant = colorants.get(str(row.get("color_index").value if row.get("color_index") else ""), "")
            name = _classify_supply(description, kind, colorant)
            if not name:
                continue
            level = row.get("level").value if row.get("level") else None
            maximum = row.get("maximum").value if row.get("maximum") else None
            unit = row.get("unit").value if row.get("unit") else None
            result.supplies[name] = {
                "name": SUPPLY_NAMES[name],
                "description": description,
                "index": index,
                "percent": _percent(level, maximum, unit),
                "level": level if isinstance(level, int) and level >= 0 else None,
                "maximum": maximum if isinstance(maximum, int) and maximum >= 0 else None,
                "unit": unit,
                "source": "SNMP",
            }
        result.online = True
    except SnmpError as exc:
        result.error = str(exc)

    return result
