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
| Tempo de atividade | `sysUpTime.0`, com conversão de TimeTicks e apresentação no painel/MQTT | Validado na unidade real |
| Estado | `hrPrinterStatus.1` traduzido para pt-BR | Pendente de teste |
| Erros | `hrPrinterDetectedErrorState.1` preservado como bits/raw | Pendente de interpretação física |
| Consumíveis | Descoberta dinâmica por tipo, descrição, unidade, capacidade, nível e cor | Cinco itens observados em dump público, não nesta unidade |
| MQTT Discovery | Device estável, entidades de leitura e disponibilidade | Implementado; requer broker/HA |
| Reboot/reset | Laboratório com catálogo fixo do `prtGeneralReset.1`, sondagem GET/GETNEXT, envio direto de um SET por clique e lote opcional dos valores 4, 5 e 6; sem espera posterior, retry ou cooldown | Nenhuma dessas escritas foi executada na unidade real nesta versão |
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
- `1.3.6.1.4.1.11` — raiz privada HP, sondada apenas com GET/GETNEXT para inventário; nenhum OID de reboot da M176n foi confirmado nessa árvore.

## Pendências para homologação

1. Cadastrar o IP real pela UI do App.
2. Testar SNMPv1 e EWS a partir do Home Assistant.
3. Confirmar estrutura real da página EWS e anonimizar fixtures.
4. Confirmar entidade e disponibilidade no MQTT Discovery.
5. O painel oferece três botões de envio direto e um lote opcional. As escritas aceitas são somente `powerCycleReset(4)`, `resetToNVRAM(5)` e `resetToFactoryDefaults(6)`; elas exigem comunidade de escrita e autorização salva, enviam SETs fixos e retornam imediatamente. Não há pré-GET, espera posterior, retry ou cooldown. Nenhum OID/valor arbitrário é aceito.
