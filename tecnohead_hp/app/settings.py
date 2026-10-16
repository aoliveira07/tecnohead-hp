"""Persistent, redacted-safe application settings."""

from __future__ import annotations

import copy
import ipaddress
import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any


DEFAULTS: dict[str, Any] = {
    "printer_name": "HP M176n",
    "ip": "",
    "dns": "",
    "snmp_port": 161,
    "snmp_version": "v1",
    "snmp_community": "",
    "snmp_write_community": "",
    "snmp_timeout": 3.0,
    "snmp_retries": 1,
    "poll_interval": 60,
    "use_ews": True,
    "ews_scheme": "http",
    "ews_port": 80,
    "ews_username": "",
    "ews_password": "",
    "mqtt_auto": True,
    "mqtt_host": "",
    "mqtt_port": 1883,
    "mqtt_username": "",
    "mqtt_password": "",
    "mqtt_tls": False,
    "alertas_suprimentos": False,
    "allow_remote_control": False,
    "allow_restart": False,
    "allow_wake": False,
    "allow_reset_test": False,
}

SECRET_FIELDS = {"snmp_community", "snmp_write_community", "ews_password", "mqtt_password"}
DATA_DIR = Path(os.environ.get("TECNHEAD_DATA_DIR", "/data"))
CONFIG_PATH = DATA_DIR / "config.json"


class SettingsError(ValueError):
    """User-provided configuration is invalid."""


def _as_bool(value: Any) -> bool:
    return bool(value) if not isinstance(value, str) else value.lower() in {"1", "true", "yes", "on"}


def validate(values: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(DEFAULTS)
    result.update({key: value for key, value in values.items() if key in DEFAULTS})
    result["printer_name"] = str(result["printer_name"]).strip() or "HP M176n"
    ip = str(result["ip"]).strip()
    if ip:
        try:
            address = ipaddress.ip_address(ip)
        except ValueError as exc:
            raise SettingsError("IP inválido: informe um endereço IPv4 da LAN.") from exc
        if address.version != 4 or address.is_loopback or address.is_multicast or address.is_unspecified or not (address.is_private or address.is_link_local):
            raise SettingsError("IP inválido: informe um endereço IPv4 privado da LAN.")
        result["ip"] = str(address)
    else:
        result["ip"] = ""
    result["dns"] = str(result["dns"]).strip()
    result["snmp_version"] = "v1"
    result["snmp_port"] = _bounded_int(result["snmp_port"], 1, 65535, "Porta SNMP")
    result["snmp_timeout"] = _bounded_float(result["snmp_timeout"], 0.1, 30.0, "Timeout SNMP")
    result["snmp_retries"] = _bounded_int(result["snmp_retries"], 1, 3, "Tentativas SNMP")
    result["poll_interval"] = _bounded_int(result["poll_interval"], 30, 86400, "Intervalo de consulta")
    result["ews_scheme"] = "http" if str(result["ews_scheme"]).lower() != "https" else "https"
    result["ews_port"] = _bounded_int(result["ews_port"], 1, 65535, "Porta EWS")
    result["mqtt_port"] = _bounded_int(result["mqtt_port"], 1, 65535, "Porta MQTT")
    result["snmp_community"] = str(result["snmp_community"])
    result["snmp_write_community"] = str(result["snmp_write_community"])
    result["ews_username"] = str(result["ews_username"])
    result["ews_password"] = str(result["ews_password"])
    result["mqtt_host"] = str(result["mqtt_host"]).strip()
    result["mqtt_username"] = str(result["mqtt_username"])
    result["mqtt_password"] = str(result["mqtt_password"])
    for key in {"use_ews", "mqtt_auto", "mqtt_tls", "alertas_suprimentos", "allow_remote_control", "allow_restart", "allow_wake", "allow_reset_test"}:
        result[key] = _as_bool(result[key])
    if result["allow_restart"] or result["allow_wake"]:
        raise SettingsError("Reiniciar e Acordar permanecem bloqueados até homologação presencial.")
    return result


def _bounded_int(value: Any, minimum: int, maximum: int, label: str) -> int:
    try:
        converted = int(value)
    except (TypeError, ValueError) as exc:
        raise SettingsError(f"{label}: valor inválido.") from exc
    if not minimum <= converted <= maximum:
        raise SettingsError(f"{label}: informe um valor entre {minimum} e {maximum}.")
    return converted


def _bounded_float(value: Any, minimum: float, maximum: float, label: str) -> float:
    try:
        converted = float(value)
    except (TypeError, ValueError) as exc:
        raise SettingsError(f"{label}: valor inválido.") from exc
    if not minimum <= converted <= maximum:
        raise SettingsError(f"{label}: informe um valor entre {minimum} e {maximum}.")
    return converted


class SettingsStore:
    def __init__(self, path: Path = CONFIG_PATH) -> None:
        self.path = path
        self._lock = threading.RLock()
        self._values = self._load()

    def _load(self) -> dict[str, Any]:
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                return validate(json.load(handle))
        except FileNotFoundError:
            return copy.deepcopy(DEFAULTS)
        except (OSError, json.JSONDecodeError, SettingsError):
            return copy.deepcopy(DEFAULTS)

    def get(self) -> dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._values)

    def save(self, incoming: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            merged = self.get()
            # Empty secret fields in the browser mean “keep current”, not erase.
            for key, value in incoming.items():
                if key in SECRET_FIELDS and value == "" and merged.get(key):
                    continue
                merged[key] = value
            values = validate(merged)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, temporary = tempfile.mkstemp(prefix="config.", suffix=".tmp", dir=str(self.path.parent))
            try:
                os.chmod(temporary, 0o600)
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(values, handle, ensure_ascii=False, indent=2)
                    handle.write("\n")
                os.replace(temporary, self.path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
            self._values = values
            return self.get()

    def public(self) -> dict[str, Any]:
        values = self.get()
        for key in SECRET_FIELDS:
            values[key] = {"configured": bool(values[key])}
        return values
