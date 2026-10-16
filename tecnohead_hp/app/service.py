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


RESET_ACTIONS: dict[str, dict[str, Any]] = {
    "power_cycle": {"value": 4, "label": "powerCycleReset(4)", "method": "power_cycle_reset", "confirmation": None},
    "nvram": {"value": 5, "label": "resetToNVRAM(5)", "method": "reset_to_nvram", "confirmation": "RESET_NVRAM"},
    "factory": {"value": 6, "label": "resetToFactoryDefaults(6)", "method": "reset_to_factory_defaults", "confirmation": "RESET_FACTORY_DEFAULTS"},
}

RESET_ENUMERATION = (
    {"value": 3, "label": "notResetting(3)", "sendable": False, "note": "Estado normal; não reinicia."},
    {"value": 4, "label": "powerCycleReset(4)", "sendable": True, "note": "Pedido padrão de ciclo de energia, se implementado."},
    {"value": 5, "label": "resetToNVRAM(5)", "sendable": True, "note": "Reset para o estado NVRAM/boot do fabricante; pode alterar configurações."},
    {"value": 6, "label": "resetToFactoryDefaults(6)", "sendable": True, "note": "Reset de fábrica; pode apagar IP, SNMP e demais configurações."},
)

RESET_PROBE_BASES = (
    ("Printer-MIB / prtGeneral", "1.3.6.1.2.1.43.5.1.1", 64),
    ("HP private enterprise MIB (somente leitura)", "1.3.6.1.4.1.11", 128),
)


class MonitorService:
    def __init__(self, store: SettingsStore | None = None) -> None:
        self.store = store or SettingsStore()
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None
        self._logs: deque[str] = deque(maxlen=200)
        self._last_reset_command_at: float | None = None
        self._reset_probe: dict[str, Any] = {"status": "not_run", "collected_at": None, "reset_oid": None, "walks": []}
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

    def reset_lab(self) -> dict[str, Any]:
        """Return the fixed reset catalog and the latest read-only probe."""

        settings = self.store.public()
        with self._lock:
            probe = json.loads(json.dumps(self._reset_probe, ensure_ascii=False))
        candidates = [
            {
                "mode": mode,
                "oid": PRT_GENERAL_RESET_OID,
                "value": action["value"],
                "label": action["label"],
                "sendable": True,
                "note": next(item["note"] for item in RESET_ENUMERATION if item["value"] == action["value"]),
            }
            for mode, action in RESET_ACTIONS.items()
        ]
        return {
            "oid": PRT_GENERAL_RESET_OID,
            "oid_name": "prtGeneralReset.1",
            "catalog": {
                "values": list(RESET_ENUMERATION),
                "candidates": candidates,
                "hp_private_enterprise_root": "1.3.6.1.4.1.11",
                "hp_private_status": "Nenhum OID de reboot HP específico da M176n foi confirmado; a raiz privada só pode ser sondada por GET.",
            },
            "ready": bool(settings.get("ip") and settings.get("allow_reset_test") and settings.get("snmp_write_community", {}).get("configured")),
            "read_community_configured": bool(settings.get("snmp_community", {}).get("configured")),
            "write_community_configured": bool(settings.get("snmp_write_community", {}).get("configured")),
            "probe": probe,
        }

    @staticmethod
    def _public_probe_value(value: Any) -> Any:
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        return str(value)

    def probe_reset_lab(self) -> dict[str, Any]:
        """Probe reset and related MIB branches with GET/GETNEXT only."""

        config = self.store.get()
        if not config.get("ip"):
            return {"ok": False, "message": "IP da impressora não configurado.", "lab": self.reset_lab()}
        if not config.get("snmp_community"):
            return {"ok": False, "message": "Configure a comunidade SNMPv1 de leitura para sondar os OIDs.", "lab": self.reset_lab()}

        client = SnmpV1Client(
            config["ip"],
            config["snmp_community"],
            config["snmp_port"],
            config["snmp_timeout"],
            config["snmp_retries"],
        )
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        probe: dict[str, Any] = {"status": "completed", "collected_at": now, "reset_oid": None, "walks": []}
        try:
            value = client.get(PRT_GENERAL_RESET_OID)
            probe["reset_oid"] = {
                "oid": PRT_GENERAL_RESET_OID,
                "status": "missing" if value is None or value.is_missing else "present",
                "tag": value.tag if value else None,
                "value": self._public_probe_value(value.value) if value else None,
                "message": "GET respondeu." if value and not value.is_missing else "No Such Name/sem valor.",
            }
        except SnmpError as exc:
            probe["reset_oid"] = {"oid": PRT_GENERAL_RESET_OID, "status": "error", "message": str(exc)}

        for label, base_oid, max_rows in RESET_PROBE_BASES:
            item: dict[str, Any] = {"label": label, "base_oid": base_oid, "status": "completed", "truncated": False, "values": []}
            try:
                values = client.walk(base_oid, max_rows=max_rows)
                item["values"] = [
                    {"oid": value.oid, "tag": value.tag, "value": self._public_probe_value(value.value)}
                    for value in values
                ]
                item["truncated"] = len(values) >= max_rows
            except SnmpError as exc:
                item["status"] = "error"
                item["message"] = str(exc)
            probe["walks"].append(item)

        with self._lock:
            self._reset_probe = probe
        self._log("Sondagem do laboratório SNMP concluída somente com GET/GETNEXT; nenhum SET foi enviado.")
        return {"ok": probe["reset_oid"].get("status") == "present", "message": "Sondagem somente leitura concluída.", "lab": self.reset_lab()}

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

    def _force_reset(self, config: dict[str, Any], mode: str = "power_cycle") -> dict[str, Any]:
        """Send one fixed reset request and return only its immediate SNMP result."""

        action = RESET_ACTIONS[mode]
        if not config.get("snmp_write_community"):
            return {"ok": False, "status": "blocked", "command_sent": False, "message": "Configure a comunidade SNMPv1 de escrita somente para o teste."}
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
            response_values = getattr(write_client, action["method"])()
            command_sent = True
        except SnmpCommandError as exc:
            command_sent = exc.command_sent
            request_error = str(exc)
        except SnmpError as exc:
            request_error = str(exc)

        if not command_sent:
            self._log(f"Teste {action['label']} não enviado: {request_error or 'falha antes do envio'}")
            return {"ok": False, "status": "send_failed", "command_sent": False, "message": "O comando não foi enviado à impressora.", "detail": request_error}

        response_ack = bool(
            response_values
            and response_values[0].oid == PRT_GENERAL_RESET_OID
            and response_values[0].tag == 0x02
            and response_values[0].value == action["value"]
        )
        self._log(f"Teste {action['label']} enviado uma única vez; confirmação posterior não foi aguardada.")
        warning = " A impressora pode perder IP, comunidade e demais configurações." if mode == "factory" else ""
        if response_ack:
            return {
                "ok": True,
                "status": "sent",
                "command_sent": True,
                "message": f"{action['label']} enviado uma única vez. Atualize o painel depois para verificar o tempo de atividade.{warning}",
                "response_ack": True,
            }
        return {
            "ok": False,
            "status": "sent_inconclusive",
            "command_sent": True,
            "message": f"O pacote {action['label']} foi enviado uma única vez, mas a impressora não confirmou a resposta. Não haverá retry; verifique o retorno e o tempo de atividade.{warning}",
            "response_ack": False,
            "request_error": request_error,
        }

    def send_reset_candidate(self, mode: str) -> dict[str, Any]:
        """Direct lab action: one fixed SET, no probe, wait, retry or cooldown."""

        if mode not in RESET_ACTIONS:
            return {"ok": False, "status": "blocked", "command_sent": False, "message": "Candidato de reset desconhecido."}
        config = self.store.get()
        if not config.get("ip"):
            return {"ok": False, "status": "blocked", "command_sent": False, "message": "IP da impressora não configurado."}
        if not config.get("allow_reset_test"):
            return {"ok": False, "status": "blocked", "command_sent": False, "message": "Marque a autorização do teste de reboot SNMP e salve."}
        return self._force_reset(config, mode)

    def send_all_reset_candidates(self) -> dict[str, Any]:
        """Send every fixed reset value in catalog order without a post-wait."""

        config = self.store.get()
        if not config.get("ip"):
            return {"ok": False, "status": "blocked", "command_sent": False, "message": "IP da impressora não configurado."}
        if not config.get("allow_reset_test"):
            return {"ok": False, "status": "blocked", "command_sent": False, "message": "Marque a autorização do teste de reboot SNMP e salve."}
        results = [self._force_reset(config, mode) | {"mode": mode} for mode in RESET_ACTIONS]
        sent = sum(1 for result in results if result.get("command_sent"))
        return {
            "ok": sent > 0,
            "status": "batch_sent",
            "command_sent": sent > 0,
            "message": f"Foram tentados {len(results)} valores do catálogo; {sent} pacote(s) foram enviados. Nenhum reboot foi aguardado.",
            "results": results,
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
            return self._force_reset(config)
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

    def test_reset(self, mode: str, confirmation: str = "") -> dict[str, Any]:
        """Run an explicitly confirmed fixed NVRAM or factory reset request."""

        action = RESET_ACTIONS.get(mode)
        if action is None or mode == "power_cycle":
            return {"ok": False, "status": "blocked", "command_sent": False, "message": "Modo de reset não permitido nesta rota."}
        if confirmation != action["confirmation"]:
            return {"ok": False, "status": "blocked", "command_sent": False, "message": f"Digite exatamente {action['confirmation']} para autorizar {action['label']}."}
        config = self.store.get()
        if not config.get("ip"):
            return {"ok": False, "status": "blocked", "command_sent": False, "message": "IP da impressora não configurado."}
        if not config.get("allow_reset_test"):
            return {"ok": False, "status": "blocked", "command_sent": False, "message": "O teste de reboot SNMP está desabilitado nas configurações."}
        return self._force_reset(config, mode)

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
