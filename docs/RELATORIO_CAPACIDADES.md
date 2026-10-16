# Relatório de capacidades — TecnoHead HP

**Revisão:** 1.0 · **Data:** 2026-10-16  
**Equipamento:** HP Color LaserJet Pro MFP M176n  
**Estado:** implementação criada; validação física pendente.

## Evidência e implementação

| Capacidade | Implementação | Estado de evidência |
|---|---|---|
| SNMPv1 | GET de identificação/estado e WALK de suprimentos | Pendente de teste na unidade real |
| EWS HTTP | GET da página principal, parser tolerante e fonte marcada | Pendente de teste na unidade real |
| Modelo | `hrDeviceDescr` e título EWS quando disponíveis | Pendente de teste |
| Uptime | `sysUpTime.0`, com conversão de TimeTicks | Pendente de teste |
| Estado | `hrPrinterStatus.1` traduzido para pt-BR | Pendente de teste |
| Erros | `hrPrinterDetectedErrorState.1` preservado como bits/raw | Pendente de interpretação física |
| Consumíveis | Descoberta dinâmica por tipo, descrição, unidade, capacidade, nível e cor | Cinco itens observados em dump público, não nesta unidade |
| MQTT Discovery | Device estável, entidades de leitura e disponibilidade | Implementado; requer broker/HA |
| Reboot | Nenhum botão; nenhum SET | Não homologado |
| Wake | Nenhum botão; nenhum pacote presumido | Não homologado |

## OIDs consultados em modo somente leitura

- `1.3.6.1.2.1.1.5.0` — nome SNMP.
- `1.3.6.1.2.1.1.3.0` — uptime.
- `1.3.6.1.2.1.25.3.2.1.3.1` — descrição do dispositivo.
- `1.3.6.1.2.1.25.3.2.1.5.1` — estado geral.
- `1.3.6.1.2.1.25.3.5.1.1.1` — estado da impressora.
- `1.3.6.1.2.1.25.3.5.1.2.1` — flags de erro.
- `1.3.6.1.2.1.43.11.1.1.*` — tabela de suprimentos.
- `1.3.6.1.2.1.43.5.1.1.3.1` — candidato a reset, consultado apenas com GET.

## Pendências para homologação

1. Cadastrar o IP real pela UI do App.
2. Testar SNMPv1 e EWS a partir do Home Assistant.
3. Confirmar estrutura real da página EWS e anonimizar fixtures.
4. Confirmar entidade e disponibilidade no MQTT Discovery.
5. Só em fase separada, com autorização explícita, avaliar reboot/wake; não executar `snmpset` automaticamente.
