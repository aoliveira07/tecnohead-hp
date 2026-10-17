# Relatório de capacidades — TecnoHead HP

**Revisão:** 1.0 · **Data:** 2026-10-16  
**Equipamento:** HP Color LaserJet Pro MFP M176n  
**Estado:** implementação criada; validação física pendente.

## Evidência e implementação

| Capacidade | Implementação | Estado de evidência |
|---|---|---|
| SNMPv1 | GET de identificação/estado e WALK de suprimentos | Pendente de teste na unidade real |
| Modelo | `hrDeviceDescr` por SNMPv1 | Pendente de teste |
| Tempo de atividade | `sysUpTime.0`, com conversão de TimeTicks e apresentação no painel/MQTT | Validado na unidade real |
| Estado | `hrPrinterStatus.1` traduzido para pt-BR | Pendente de teste |
| Erros | `hrPrinterDetectedErrorState.1` preservado como bits/raw | Pendente de interpretação física |
| Consumíveis | Descoberta dinâmica por tipo, descrição, unidade, capacidade, nível e cor | Cinco itens observados em dump público, não nesta unidade |
| MQTT Discovery | Device estável, entidades de leitura e disponibilidade | Implementado; requer broker/HA |
| Rotina Sonoff/Tasmota | `homeassistant.turn_off` diário para entidade configurada; religamento fica no Tasmota | Implementado; requer API do Home Assistant e entidade válida |
| Controle da impressora | Nenhuma escrita SNMP ou comando de energia direto | Não disponível por decisão de segurança |

## OIDs consultados em modo somente leitura

- `1.3.6.1.2.1.1.5.0` — nome SNMP.
- `1.3.6.1.2.1.1.3.0` — uptime.
- `1.3.6.1.2.1.25.3.2.1.3.1` — descrição do dispositivo.
- `1.3.6.1.2.1.25.3.2.1.5.1` — estado geral.
- `1.3.6.1.2.1.25.3.5.1.1.1` — estado da impressora.
- `1.3.6.1.2.1.25.3.5.1.2.1` — flags de erro.
- `1.3.6.1.2.1.43.11.1.1.*` — tabela de suprimentos.

## Pendências para homologação

1. Cadastrar o IP real pela UI do App.
2. Testar SNMPv1 a partir do Home Assistant.
3. Confirmar entidade e disponibilidade no MQTT Discovery.
4. Testar o horário configurado com o Sonoff/Tasmota desligando e religando pelo próprio firmware.
5. O painel da impressora permanece somente leitura. Não há OIDs de escrita, comandos de reboot, reset de fábrica ou Wake-on-LAN.
