"""Capability and command guardrails for the real-device homologation phase."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Capability:
    name: str
    status: str
    evidence: str
    destructive: bool = False


READ_ONLY_CAPABILITIES = (
    Capability("SNMPv1 GET/WALK", "implemented", "cliente local somente leitura"),
    Capability("EWS HTTP GET", "implemented", "página principal, parser tolerante"),
    Capability("MQTT Discovery", "implemented", "payloads estáveis e disponibilidade"),
    Capability("Reiniciar impressora", "unavailable", "não homologado na unidade real", destructive=True),
    Capability("Acordar impressora", "unavailable", "Wake-on-LAN não presumido", destructive=True),
)


def command_allowed(command: str, *, enabled: bool, capability_validated: bool, printer_state: str, cooldown_ok: bool) -> tuple[bool, str]:
    """Apply backend guardrails; UI flags alone are never sufficient."""

    if command not in {"restart", "wake"}:
        return False, "Comando desconhecido."
    if not enabled:
        return False, "Controles remotos estão desabilitados."
    if not capability_validated:
        return False, "A capacidade ainda não foi homologada na impressora real."
    if printer_state in {"printing", "warmup", "error", "unknown"}:
        return False, "Comando bloqueado no estado atual da impressora."
    if not cooldown_ok:
        return False, "Aguarde o intervalo de segurança antes de repetir o comando."
    return True, "Autorizado pela política; execução ainda requer procedimento específico."
