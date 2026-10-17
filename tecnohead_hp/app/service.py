"""Application lifecycle, polling and state normalization."""

from __future__ import annotations

import datetime as dt
import json
import threading
from collections import deque
from typing import Any

from home_assistant import turn_off
from mqtt_discovery import MqttPublisher
from printer_state import CollectionResult, collect
from settings import SettingsStore
from snmp_client import SnmpError, SnmpV1Client


class MonitorService:
    def __init__(self, store: SettingsStore | None = None) -> None:
        self.store = store or SettingsStore()
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._schedule_stop = threading.Event()
        self._schedule_wake = threading.Event()
        self._thread: threading.Thread | None = None
        self._schedule_thread: threading.Thread | None = None
        self._last_tasmota_schedule: tuple[str, str, str] | None = None
        self._logs: deque[str] = deque(maxlen=200)
        self._state: dict[str, Any] = self._waiting_state("Aguardando configuração da impressora.")
        self.mqtt = MqttPublisher(self.store.get, self._log)

    def _log(self, message: str) -> None:
        line = f"{dt.datetime.now(dt.timezone.utc).isoformat()} {message}"
        with self._lock:
            self._logs.append(line)

    def start(self) -> None:
        if not self._thread or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._run, name="tecnohead-monitor", daemon=True)
            self._thread.start()
        if self._schedule_thread and self._schedule_thread.is_alive():
            return
        self._schedule_stop.clear()
        self._schedule_thread = threading.Thread(target=self._run_tasmota_schedule, name="tecnohead-tasmota", daemon=True)
        self._schedule_thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        self._schedule_stop.set()
        self._schedule_wake.set()
        if self._thread:
            self._thread.join(timeout=5)
        if self._schedule_thread:
            self._schedule_thread.join(timeout=5)
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
            "sources": {},
        }

    def _run(self) -> None:
        self._log("TecnoHead HP iniciado em modo de monitoramento.")
        while not self._stop.is_set():
            self.refresh()
            config = self.store.get()
            interval = int(config.get("poll_interval", 60))
            self._wake.wait(timeout=max(1, interval))
            self._wake.clear()

    def _run_tasmota_schedule(self) -> None:
        self._log("Rotina Tasmota iniciada.")
        while not self._schedule_stop.is_set() and not self._stop.is_set():
            self._check_tasmota_schedule()
            self._schedule_wake.wait(timeout=15)
            self._schedule_wake.clear()

    def _check_tasmota_schedule(self) -> None:
        config = self.store.get()
        entity_id = str(config.get("tasmota_entity", ""))
        off_time = str(config.get("tasmota_off_time", ""))
        if not entity_id or not off_time:
            return
        now = dt.datetime.now()
        if now.strftime("%H:%M") != off_time:
            return
        schedule_key = (now.date().isoformat(), entity_id, off_time)
        with self._lock:
            if self._last_tasmota_schedule == schedule_key:
                return
            self._last_tasmota_schedule = schedule_key
        ok, message = turn_off(entity_id)
        prefix = "Rotina Tasmota concluída" if ok else "Rotina Tasmota falhou"
        self._log(f"{prefix}: {message}")

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
        new_state.update({"configured": True, "app_online": True, "message": result.error or ("Leitura concluída." if result.online else "Impressora sem resposta.")})
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
        self._schedule_wake.set()
        return self.status()

    def test_connection(self) -> dict[str, Any]:
        config = self.store.get()
        if not config.get("ip"):
            return {"ok": False, "message": "IP da impressora não configurado."}
        result = collect(config)
        return {"ok": result.online, "message": result.error or ("SNMPv1 conectado." if result.online else "SNMPv1 sem resposta."), "result": result.public()}

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

    def diagnostics(self) -> dict[str, Any]:
        status = self.status()
        with self._lock:
            status["logs"] = list(self._logs)
        return status

    def export_diagnostics(self) -> dict[str, Any]:
        data = self.diagnostics()
        data.pop("settings", None)
        return data
