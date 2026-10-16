"""Application lifecycle, polling and state normalization."""

from __future__ import annotations

import datetime as dt
import json
import threading
import time
from collections import deque
from typing import Any

from ews_client import fetch_ews
from mqtt_discovery import MqttPublisher
from printer_state import CollectionResult, collect
from settings import SettingsError, SettingsStore
from snmp_client import SnmpError, SnmpV1Client


class MonitorService:
    def __init__(self, store: SettingsStore | None = None) -> None:
        self.store = store or SettingsStore()
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None
        self._logs: deque[str] = deque(maxlen=200)
        self._state: dict[str, Any] = self._waiting_state("Aguardando configuração da impressora.")
        self.mqtt = MqttPublisher(self.store.get, self._log)

    def _log(self, message: str) -> None:
        line = f"{dt.datetime.now(dt.timezone.utc).isoformat()} {message}"
        with self._lock:
            self._logs.append(line)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name="tecnohead-monitor", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread:
            self._thread.join(timeout=5)
        self.mqtt.close()

    def _waiting_state(self, message: str) -> dict[str, Any]:
        return {
            "configured": False,
            "app_online": True,
            "online": False,
            "state": "unknown",
            "state_label": "Desconhecida",
            "message": message,
            "collected_at": None,
            "supplies": {},
            "ews": {},
            "sources": {},
            "reset_oid_present": False,
            "last_command": "não disponível",
        }

    def _run(self) -> None:
        self._log("TecnoHead HP iniciado; comandos remotos permanecem bloqueados.")
        while not self._stop.is_set():
            self.refresh()
            config = self.store.get()
            interval = int(config.get("poll_interval", 60))
            self._wake.wait(timeout=max(1, interval))
            self._wake.clear()

    def refresh(self) -> dict[str, Any]:
        config = self.store.get()
        if not config.get("ip"):
            with self._lock:
                self._state = self._waiting_state("Aguardando configuração da impressora.")
            self.mqtt.clear_discovery()
            self.mqtt.publish_app_availability(True)
            return self.status()
        result: CollectionResult = collect(config)
        new_state = result.public()
        new_state.update({"configured": True, "app_online": True, "message": result.error or ("Leitura concluída." if result.online else "Impressora sem resposta."), "last_command": "não disponível"})
        with self._lock:
            self._state = new_state
        if self.mqtt.ensure_connected():
            self.mqtt.publish_discovery(new_state)
            self.mqtt.publish_state(new_state)
        return self.status()

    def status(self) -> dict[str, Any]:
        with self._lock:
            state = json.loads(json.dumps(self._state, ensure_ascii=False))
            state["mqtt_connected"] = self.mqtt.connected
            state["settings"] = self.store.public()
            return state

    def save(self, incoming: dict[str, Any]) -> dict[str, Any]:
        before = self.store.get()
        values = self.store.save(incoming)
        if before.get("ip") != values.get("ip"):
            with self._lock:
                self._state = self._waiting_state("Endereço alterado; aguardando nova leitura.")
            self._log("Endereço da impressora alterado; estado anterior invalidado.")
            self.mqtt.clear_discovery()
        self._wake.set()
        return self.status()

    def test_connection(self) -> dict[str, Any]:
        config = self.store.get()
        if not config.get("ip"):
            return {"ok": False, "message": "IP da impressora não configurado."}
        result = collect(config)
        return {"ok": result.online, "message": result.error or ("SNMP/EWS conectado." if result.online else "Nenhuma fonte respondeu."), "result": result.public()}

    def test_snmp(self) -> dict[str, Any]:
        config = self.store.get()
        if not config.get("ip"):
            return {"ok": False, "message": "IP da impressora não configurado."}
        if not config.get("snmp_community"):
            return {"ok": False, "message": "Comunidade SNMPv1 não configurada."}
        try:
            client = SnmpV1Client(config["ip"], config["snmp_community"], config["snmp_port"], config["snmp_timeout"], config["snmp_retries"])
            value = client.get("1.3.6.1.2.1.1.5.0")
            return {"ok": bool(value and not value.is_missing), "message": "SNMPv1 respondeu." if value else "SNMP sem resposta.", "name": value.value if value else None}
        except SnmpError as exc:
            return {"ok": False, "message": str(exc)}

    def test_ews(self) -> dict[str, Any]:
        config = self.store.get()
        if not config.get("ip"):
            return {"ok": False, "message": "IP da impressora não configurado."}
        result = fetch_ews(config["ip"], scheme=config["ews_scheme"], port=config["ews_port"], username=config["ews_username"], password=config["ews_password"], timeout=config["snmp_timeout"])
        return {"ok": result.reachable, "message": "EWS respondeu." if result.reachable else (result.error or "EWS sem resposta."), "result": result.public()}

    def test_mqtt(self) -> dict[str, Any]:
        ok, message = self.mqtt.test()
        return {"ok": ok, "message": message}

    def discover(self) -> dict[str, Any]:
        result = self.test_connection()
        result["read_only"] = True
        result["reset_oid_note"] = "A presença do OID não autoriza SNMP SET; reboot continua bloqueado."
        return result

    def diagnostics(self) -> dict[str, Any]:
        status = self.status()
        with self._lock:
            status["logs"] = list(self._logs)
        status["capabilities"] = {
            "reboot": {"status": "unavailable", "reason": "não homologado na unidade real"},
            "wake": {"status": "unavailable", "reason": "não comprovado; não presumir Wake-on-LAN"},
        }
        return status

    def export_diagnostics(self) -> dict[str, Any]:
        data = self.diagnostics()
        data.pop("settings", None)
        return data
