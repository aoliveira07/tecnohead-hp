"""Small Home Assistant Core API client used by the scheduled Tasmota action."""

from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


HOME_ASSISTANT_API = "http://supervisor/core/api"


def turn_off(entity_id: str, *, timeout: float = 5.0) -> tuple[bool, str]:
    """Ask Home Assistant to turn off one configured entity."""

    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        return False, "API do Home Assistant indisponível: SUPERVISOR_TOKEN não encontrado."

    payload = json.dumps({"entity_id": entity_id}).encode("utf-8")
    request = Request(
        f"{HOME_ASSISTANT_API}/services/homeassistant/turn_off",
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "TecnoHead-HP/1.0",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=max(0.5, min(float(timeout), 30.0))) as response:
            if 200 <= int(getattr(response, "status", 200)) < 300:
                return True, f"Comando OFF enviado para {entity_id}."
            return False, f"Home Assistant respondeu HTTP {getattr(response, 'status', 'desconhecido')}."
    except HTTPError as exc:
        return False, f"Home Assistant respondeu HTTP {exc.code} ao enviar OFF."
    except (URLError, TimeoutError, OSError) as exc:
        return False, f"Não foi possível enviar OFF ao Home Assistant: {type(exc).__name__}."
