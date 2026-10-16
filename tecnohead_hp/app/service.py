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
from printer_state import CollectionResult, OID_UPTIME, collect
from settings import SettingsError, SettingsStore
from snmp_client import POWER_CYCLE_RESET_VALUE, PRT_GENERAL_RESET_OID, SnmpCommandError, SnmpError, SnmpV1Client, ticks_to_seconds


class MonitorService:
    def __init__(self, store: SettingsStore | None = None) -> None:
        self.store = store or SettingsStore()
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None
        self._logs: deque[str] = deque(maxlen=200)
        self._last_reset_command_at: float | None = None
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

    def _claim_reset_slot(self) -> dict[str, Any] | None:
        with self._lock:
            if self._last_reset_command_at is not None:
                elapsed = time.monotonic() - self._last_reset_command_at
                if elapsed < 600:
                    remaining = max(1, int(600 - elapsed))
                    return {
                        "ok": False,
                        "status": "cooldown",
                        "command_sent": False,
                        "message": f"Aguarde {remaining} segundos antes de uma nova tentativa; o último envio pode ter reiniciado a impressora.",
                    }
            self._last_reset_command_at = time.monotonic()
        return None

    def _release_reset_slot(self) -> None:
        with self._lock:
            self._last_reset_command_at = None

    def _force_reboot(self, config: dict[str, Any]) -> dict[str, Any]:
        """Send the fixed power-cycle request without the optional-OID probe."""

        if not config.get("snmp_write_community"):
            return {"ok": False, "status": "blocked", "command_sent": False, "message": "Configure a comunidade SNMPv1 de escrita somente para o teste forçado."}
        current = self.status()
        if not current.get("online"):
            return {"ok": False, "status": "blocked", "command_sent": False, "message": "A impressora não está online para o teste forçado."}
        if current.get("state") in {"printing", "warmup", "error", "unknown"}:
            return {"ok": False, "status": "blocked", "command_sent": False, "message": f"Teste forçado bloqueado no estado atual: {current.get('state_label', 'desconhecido')}."}
        cooldown = self._claim_reset_slot()
        if cooldown:
            return cooldown

        write_client = SnmpV1Client(
            config["ip"],
            config["snmp_write_community"],
            config["snmp_port"],
            config["snmp_timeout"],
            retries=1,
        )
        command_sent = False
        request_error: str | None = None
        response_values = []
        try:
            response_values = write_client.power_cycle_reset()
            command_sent = True
        except SnmpCommandError as exc:
            command_sent = exc.command_sent
            request_error = str(exc)
        except SnmpError as exc:
            request_error = str(exc)

        if not command_sent:
            self._release_reset_slot()
            self._log(f"Teste forçado de reboot não enviado: {request_error or 'falha antes do envio'}")
            return {"ok": False, "status": "send_failed", "command_sent": False, "message": "O comando forçado não foi enviado à impressora.", "detail": request_error}

        response_ack = bool(
            response_values
            and response_values[0].oid == PRT_GENERAL_RESET_OID
            and response_values[0].tag == 0x02
            and response_values[0].value == POWER_CYCLE_RESET_VALUE
        )
        self._log("Teste forçado enviado uma única vez: powerCycleReset(4); confirmação posterior não foi aguardada.")
        if response_ack:
            return {
                "ok": True,
                "status": "sent",
                "command_sent": True,
                "message": "powerCycleReset(4) enviado uma única vez. Atualize o painel depois que a impressora retornar para verificar o tempo de atividade.",
                "response_ack": True,
            }
        return {
            "ok": False,
            "status": "sent_inconclusive",
            "command_sent": True,
            "message": "O pacote foi enviado uma única vez, mas a impressora não confirmou a resposta. Não haverá retry; verifique o retorno e o tempo de atividade.",
            "response_ack": False,
            "request_error": request_error,
        }

    def _verify_reset(self, client: SnmpV1Client, previous_uptime: float | None) -> dict[str, Any]:
        """Observe the printer after a one-shot command using GET only."""

        deadline = time.monotonic() + 30.0
        saw_disconnect = False
        last_uptime: float | None = None
        while time.monotonic() < deadline:
            time.sleep(min(2.0, max(0.1, deadline - time.monotonic())))
            try:
                value = client.get(OID_UPTIME)
            except SnmpError:
                saw_disconnect = True
                continue
            if value is None or value.is_missing:
                saw_disconnect = True
                continue
            last_uptime = ticks_to_seconds(value.value)
            if previous_uptime is not None and last_uptime is not None and last_uptime < previous_uptime:
                return {
                    "status": "verified",
                    "saw_disconnect": saw_disconnect,
                    "uptime_before": previous_uptime,
                    "uptime_after": last_uptime,
                }
        return {
            "status": "inconclusive",
            "saw_disconnect": saw_disconnect,
            "uptime_before": previous_uptime,
            "uptime_after": last_uptime,
        }

    def test_reboot(self, *, force: bool = False) -> dict[str, Any]:
        """Run the supervised, one-shot Printer-MIB power-cycle test."""

        config = self.store.get()
        if not config.get("ip"):
            return {"ok": False, "status": "blocked", "command_sent": False, "message": "IP da impressora não configurado."}
        if not config.get("allow_reset_test"):
            return {"ok": False, "status": "blocked", "command_sent": False, "message": "O teste de reboot SNMP está desabilitado nas configurações."}
        if force:
            return self._force_reboot(config)
        if not config.get("snmp_community"):
            return {"ok": False, "status": "blocked", "command_sent": False, "message": "Configure a comunidade SNMPv1 de leitura para fazer a pré-verificação."}

        read_client = SnmpV1Client(
            config["ip"],
            config["snmp_community"],
            config["snmp_port"],
            config["snmp_timeout"],
            config["snmp_retries"],
        )
        try:
            probe = read_client.get(PRT_GENERAL_RESET_OID)
        except SnmpError as exc:
            message = str(exc)
            if "error-status=" in message:
                self._log("Homologação de reboot bloqueada: prtGeneralReset não foi confirmado por GET; nenhum SET foi enviado.")
                return {
                    "ok": False,
                    "status": "unavailable",
                    "command_sent": False,
                    "message": "A impressora não confirmou o OID prtGeneralReset por GET; nenhum SNMP SET foi enviado.",
                    "detail": message,
                }
            return {"ok": False, "status": "preflight_failed", "command_sent": False, "message": f"Não foi possível verificar o OID de reboot: {message}"}
        if probe is None or probe.is_missing:
            self._log("Homologação de reboot bloqueada: prtGeneralReset ausente; nenhum SET foi enviado.")
            return {
                "ok": False,
                "status": "unavailable",
                "command_sent": False,
                "message": "A impressora não confirmou o OID prtGeneralReset por GET; nenhum SNMP SET foi enviado.",
            }
        if probe.tag != 0x02 or probe.value not in {3, POWER_CYCLE_RESET_VALUE}:
            self._log("Homologação de reboot bloqueada: prtGeneralReset retornou tipo/estado incompatível.")
            return {
                "ok": False,
                "status": "unavailable",
                "command_sent": False,
                "message": "O OID de reboot respondeu com tipo ou estado incompatível; nenhum SNMP SET foi enviado.",
                "value": probe.value,
            }
        if not config.get("snmp_write_community"):
            return {"ok": False, "status": "blocked", "command_sent": False, "message": "Configure a comunidade SNMPv1 de escrita somente para o teste supervisionado."}

        before = collect(config)
        if not before.online:
            return {"ok": False, "status": "blocked", "command_sent": False, "message": "A impressora não está online para o teste supervisionado."}
        if before.state in {"printing", "warmup", "error", "unknown"}:
            return {"ok": False, "status": "blocked", "command_sent": False, "message": f"Teste bloqueado no estado atual: {before.state_label}."}

        cooldown = self._claim_reset_slot()
        if cooldown:
            return cooldown

        write_client = SnmpV1Client(
            config["ip"],
            config["snmp_write_community"],
            config["snmp_port"],
            config["snmp_timeout"],
            retries=1,
        )
        command_sent = False
        request_error: str | None = None
        response_values = []
        try:
            response_values = write_client.power_cycle_reset()
            command_sent = True
        except SnmpCommandError as exc:
            command_sent = exc.command_sent
            request_error = str(exc)
        except SnmpError as exc:
            request_error = str(exc)

        if not command_sent:
            self._release_reset_slot()
            self._log(f"Homologação de reboot não enviada: {request_error or 'falha antes do envio'}")
            return {"ok": False, "status": "send_failed", "command_sent": False, "message": "O comando não foi enviado à impressora.", "detail": request_error}

        verification = self._verify_reset(read_client, before.uptime_seconds)
        response_ack = bool(
            response_values
            and response_values[0].oid == PRT_GENERAL_RESET_OID
            and response_values[0].tag == 0x02
            and response_values[0].value == POWER_CYCLE_RESET_VALUE
        )
        if verification["status"] == "verified":
            self._log("Homologação de reboot concluída: powerCycleReset(4) e queda do uptime confirmados.")
            return {
                "ok": True,
                "status": "verified",
                "command_sent": True,
                "message": "Reinício SNMP confirmado pelo retorno da impressora e pela redução do tempo de atividade.",
                "response_ack": response_ack,
                "verification": verification,
                "request_error": request_error,
            }

        self._log("Homologação de reboot inconclusiva após um único envio; nenhum retry será executado.")
        return {
            "ok": False,
            "status": "inconclusive",
            "command_sent": True,
            "message": "A solicitação foi enviada uma única vez, mas o reinício não pôde ser confirmado; ela não será repetida automaticamente.",
            "response_ack": response_ack,
            "verification": verification,
            "request_error": request_error,
        }

    def discover(self) -> dict[str, Any]:
        result = self.test_connection()
        result["read_only"] = True
        result["reset_oid_note"] = "O reboot só é testado após GET positivo, autorização explícita e estado ocioso; ausência do OID bloqueia o SET."
        return result

    def diagnostics(self) -> dict[str, Any]:
        status = self.status()
        with self._lock:
            status["logs"] = list(self._logs)
        reset_present = bool(status.get("reset_oid_present"))
        status["capabilities"] = {
            "reboot": {
                "status": "ready_for_supervised_test" if reset_present and status["settings"].get("allow_reset_test") and status["settings"].get("snmp_write_community", {}).get("configured") else ("available_but_disabled" if reset_present else "unavailable"),
                "reason": "prtGeneralReset confirmado por GET; teste ainda supervisionado" if reset_present else "prtGeneralReset não confirmado por GET na unidade real",
            },
            "wake": {"status": "unavailable", "reason": "não comprovado; não presumir Wake-on-LAN"},
        }
        return status

    def export_diagnostics(self) -> dict[str, Any]:
        data = self.diagnostics()
        data.pop("settings", None)
        return data
