"""Remote-command policy.

The V1 App intentionally does not register reboot/wake MQTT entities. This
module exists so a future homologated command cannot bypass the backend guard.
"""

from __future__ import annotations

from capabilities import command_allowed


def handle_command(command: str, *, config: dict, printer_state: str, capability_validated: bool = False, cooldown_ok: bool = False) -> dict[str, str | bool]:
    allowed, reason = command_allowed(
        command,
        enabled=bool(config.get("allow_remote_control")),
        capability_validated=capability_validated,
        printer_state=printer_state,
        cooldown_ok=cooldown_ok,
    )
    return {"accepted": allowed, "command": command, "result": "not_implemented" if not allowed else "pending_homologation", "message": reason}
