# TecnoHead HP

App para Home Assistant OS que monitora localmente a **HP Color LaserJet Pro MFP M176n** por SNMPv1, publica sensores por MQTT Discovery e oferece uma interface Ingress em português para cadastrar e testar o endereço IP da impressora.

> A comunicação com a impressora opera somente em leitura: o App não envia comandos de escrita nem reinício remoto. A rotina opcional do Sonoff/Tasmota é um controle externo feito pela API do Home Assistant.

## Instalação

1. No Home Assistant, abra **Configurações → Apps → Repositórios**.
2. Adicione a URL deste repositório.
3. Instale **TecnoHead HP** e abra o painel Ingress.
4. Informe o IP da impressora na tela **Configurações**. O campo começa vazio por segurança.
5. Informe a comunidade SNMPv1 de leitura e clique em **Salvar configurações** e **Testar conexão**.

O App não exige edição de `configuration.yaml`, não depende de Wi-Fi ou nuvem e não publica portas na LAN. O broker MQTT do Home Assistant é descoberto automaticamente pelo Supervisor.

## Estado da implementação

- SNMPv1: GET e WALK somente leitura, com descoberta dinâmica de consumíveis.
- MQTT Discovery: dispositivo único com identificadores estáveis e disponibilidade separada do App.
- Rotina diária opcional: envia `homeassistant.turn_off` para uma entidade Sonoff/Tasmota no horário configurado; o religamento fica a cargo do Tasmota.
- IP vazio: painel funcional, monitoramento suspenso e nenhuma entidade de impressora criada.
- Controle direto da impressora: não disponível; a rotina externa do Sonoff/Tasmota envia apenas OFF no horário configurado.

Leia [`tecnohead_hp/README.md`](tecnohead_hp/README.md), [`tecnohead_hp/DOCS.md`](tecnohead_hp/DOCS.md) e [`docs/RELATORIO_CAPACIDADES.md`](docs/RELATORIO_CAPACIDADES.md) para detalhes, segurança, rollback e limitações.

## Desenvolvimento local

```bash
python -m unittest discover -s tests -t . -v
```

O projeto usa Dockerfile moderno e não contém `build.yaml` legado.
