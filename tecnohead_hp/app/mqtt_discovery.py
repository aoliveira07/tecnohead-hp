"""MQTT Discovery publisher with optional Supervisor MQTT service lookup."""

from __future__ import annotations

import json
import os
import socket
import ssl
import threading
from typing import Any, Callable
from urllib.request import Request, urlopen


BASE_TOPIC = "tecnohead_hp/printers/m176n_01"
DEVICE_ID = "tecnohead_hp_m176n_01"
DISCOVERY_PREFIX = "homeassistant"
SUPPLY_KEYS = ("preto", "ciano", "magenta", "amarelo", "cilindro_imagem")


def _device() -> dict[str, Any]:
    return {
        "identifiers": [DEVICE_ID],
        "name": "TecnoHead HP · HP M176n",
        "manufacturer": "HP",
        "model": "HP Color LaserJet Pro MFP M176n",
        "via_device": "tecnohead_hp",
    }


def build_discovery_payloads(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return only entities backed by real state, never presumed capabilities."""

    if not state.get("configured"):
        return {}
    availability = f"{BASE_TOPIC}/availability"
    state_topic = f"{BASE_TOPIC}/state"
    common = {
        "availability_topic": availability,
        "payload_available": "online",
        "payload_not_available": "offline",
        "state_topic": state_topic,
        "json_attributes_topic": state_topic,
        "device": _device(),
    }
    payloads: dict[str, dict[str, Any]] = {}

    def add(component: str, key: str, payload: dict[str, Any]) -> None:
        topic = f"{DISCOVERY_PREFIX}/{component}/{DEVICE_ID}_{key}/config"
        payloads[topic] = payload

    add(
        "binary_sensor",
        "online",
        {
            **common,
            "name": "Online",
            "unique_id": f"{DEVICE_ID}_online",
            "device_class": "connectivity",
            "payload_on": "true",
            "payload_off": "false",
            "value_template": "{{ 'true' if value_json.online else 'false' }}",
        },
    )
    add(
        "sensor",
        "estado",
        {
            **common,
            "name": "Estado",
            "unique_id": f"{DEVICE_ID}_estado",
            "value_template": "{{ value_json.state_label | default('Desconhecida') }}",
        },
    )
    add(
        "binary_sensor",
        "erro",
        {
            **common,
            "name": "Erro",
            "unique_id": f"{DEVICE_ID}_erro",
            "device_class": "problem",
            "payload_on": "true",
            "payload_off": "false",
            "value_template": "{{ 'true' if value_json.state == 'error' else 'false' }}",
        },
    )
    add(
        "sensor",
        "tempo_ligada",
        {
            **common,
            "name": "Tempo de atividade",
            "unique_id": f"{DEVICE_ID}_tempo_ligada",
            "unit_of_measurement": "s",
            "state_class": "measurement",
            "device_class": "duration",
            "value_template": "{{ value_json.uptime_seconds if value_json.uptime_seconds is not none else 'unknown' }}",
        },
    )
    add(
        "sensor",
        "ultima_leitura",
        {
            **common,
            "name": "Última leitura",
            "unique_id": f"{DEVICE_ID}_ultima_leitura",
            "device_class": "timestamp",
            "entity_category": "diagnostic",
            "value_template": "{{ value_json.collected_at }}",
        },
    )
    for key in SUPPLY_KEYS:
        supply = (state.get("supplies") or {}).get(key)
        if not supply:
            continue
        add(
            "sensor",
            f"toner_{key}",
            {
                **common,
                "name": supply.get("name", key.replace("_", " ").title()),
                "unique_id": f"{DEVICE_ID}_toner_{key}",
                "unit_of_measurement": "%",
                "state_class": "measurement",
                "value_template": f"{{{{ value_json.supplies.{key}.percent if value_json.supplies.{key}.percent is not none else 'unknown' }}}}",
            },
        )
    return payloads


def _supervisor_mqtt() -> dict[str, Any] | None:
    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        return None
    request = Request("http://supervisor/services/mqtt", headers={"Authorization": f"Bearer {token}"}, method="GET")
    try:
        with urlopen(request, timeout=2.0) as response:
            body = json.loads(response.read().decode("utf-8"))
            # Supervisor services return the service description under
            # ``data``. Accept the direct shape as well for compatibility
            # with development stubs and older Supervisor versions.
            data = body.get("data") if isinstance(body, dict) else None
            connection = data if isinstance(data, dict) else body
            if not isinstance(connection, dict) or not connection.get("host"):
                return None
            return {
                "host": connection["host"],
                "port": int(connection.get("port", 1883)),
                "username": connection.get("username", ""),
                "password": connection.get("password", ""),
                "ssl": bool(connection.get("ssl", False)),
            }
    except Exception:
        return None


class MqttPublisher:
    def __init__(self, config_getter: Callable[[], dict[str, Any]], log: Callable[[str], None] | None = None) -> None:
        self.config_getter = config_getter
        self.log = log or (lambda _message: None)
        self._client: Any = None
        self._connection: dict[str, Any] | None = None
        self._connected = False
        self._lock = threading.RLock()

    def _resolve(self) -> dict[str, Any] | None:
        if self.config_getter().get("mqtt_auto", True):
            return _supervisor_mqtt()
        return None

    @property
    def connected(self) -> bool:
        return self._connected

    def _create_client(self, connection: dict[str, Any]) -> Any:
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            return None
        try:
            client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="tecnohead_hp_m176n")
        except (AttributeError, TypeError):
            client = mqtt.Client(client_id="tecnohead_hp_m176n")
        if connection.get("username"):
            client.username_pw_set(connection["username"], connection.get("password", ""))
        if connection.get("ssl"):
            client.tls_set(cert_reqs=ssl.CERT_REQUIRED)
        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        return client

    def _on_connect(self, _client: Any, _userdata: Any, _flags: Any, reason_code: Any, *_extra: Any) -> None:
        try:
            code = int(reason_code)
        except (TypeError, ValueError):
            code = getattr(reason_code, "value", None)
            if code is None:
                code = 0 if str(reason_code).lower() in {"success", "0"} else 1
        self._connected = code == 0

    def _on_disconnect(self, _client: Any, _userdata: Any, _flags: Any = None, _reason_code: Any = None, *_extra: Any) -> None:
        self._connected = False

    def ensure_connected(self) -> bool:
        with self._lock:
            connection = self._resolve()
            if not connection:
                self._connected = False
                return False
            if self._connected and self._connection == connection and self._client is not None:
                return True
            self.close()
            client = self._create_client(connection)
            if client is None:
                self.log("MQTT indisponível: biblioteca paho-mqtt não instalada.")
                return False
            try:
                client.connect(connection["host"], int(connection["port"]), keepalive=60)
                client.loop_start()
                self._client = client
                self._connection = connection
                return True
            except Exception as exc:
                self._connected = False
                self.log(f"MQTT indisponível: {type(exc).__name__}.")
                try:
                    client.loop_stop()
                except Exception:
                    pass
                return False

    def test(self) -> tuple[bool, str]:
        connection = self._resolve()
        if not connection:
            return False, "Nenhum broker MQTT foi descoberto ou configurado."
        try:
            host = connection.get("host")
            port = connection.get("port")
            if not host or not port:
                return False, "Dados do broker MQTT incompletos."
            with socket.create_connection((str(host), int(port)), timeout=3.0):
                pass
            return True, "TCP do broker MQTT respondeu; autenticação será validada na publicação."
        except OSError as exc:
            return False, f"Broker MQTT indisponível: {type(exc).__name__}."

    def publish(self, topic: str, payload: str, *, retain: bool = False) -> bool:
        if not self.ensure_connected() or self._client is None:
            return False
        try:
            result = self._client.publish(topic, payload, qos=0, retain=retain)
            return getattr(result, "rc", 0) == 0
        except Exception:
            self._connected = False
            return False

    def publish_app_availability(self, online: bool) -> None:
        self.publish(f"{BASE_TOPIC}/app_availability", "online" if online else "offline", retain=True)

    def publish_state(self, state: dict[str, Any]) -> bool:
        if not state.get("configured"):
            return False
        self.publish_app_availability(True)
        availability = "online" if state.get("online") else "offline"
        self.publish(f"{BASE_TOPIC}/availability", availability, retain=True)
        return self.publish(f"{BASE_TOPIC}/state", json.dumps(state, ensure_ascii=False), retain=True)

    def publish_discovery(self, state: dict[str, Any]) -> int:
        if not state.get("configured") or not self.ensure_connected():
            return 0
        count = 0
        for topic, payload in build_discovery_payloads(state).items():
            if self.publish(topic, json.dumps(payload, ensure_ascii=False), retain=True):
                count += 1
        return count

    def clear_discovery(self) -> None:
        if not self.ensure_connected():
            return
        topics = [f"{DISCOVERY_PREFIX}/{component}/{DEVICE_ID}_{key}/config" for component, key in (("binary_sensor", "online"), ("sensor", "estado"), ("binary_sensor", "erro"), ("sensor", "tempo_ligada"), ("sensor", "ultima_leitura"))]
        topics.extend(f"{DISCOVERY_PREFIX}/sensor/{DEVICE_ID}_toner_{key}/config" for key in SUPPLY_KEYS)
        for topic in topics:
            self.publish(topic, "", retain=True)

    def close(self) -> None:
        with self._lock:
            if self._client is not None:
                try:
                    self._client.loop_stop()
                    self._client.disconnect()
                except Exception:
                    pass
            self._client = None
            self._connection = None
            self._connected = False
