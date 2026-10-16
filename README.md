# TecnoHead HP

App para Home Assistant OS que monitora localmente a **HP Color LaserJet Pro MFP M176n** por SNMPv1 e HTTP/EWS, publica sensores por MQTT Discovery e oferece uma interface Ingress em português para cadastrar, testar e alterar o endereço IP da impressora.

> V1: monitoramento somente leitura, com uma porta de homologação supervisionada para avaliar `powerCycleReset(4)` sem disponibilizar um comando de produção antes da comprovação.

## Instalação

1. No Home Assistant, abra **Configurações → Apps → Repositórios**.
2. Adicione a URL deste repositório.
3. Instale **TecnoHead HP** e abra o painel Ingress.
4. Informe o IP da impressora na tela **Configurações**. O campo começa vazio por segurança.
5. Informe a comunidade SNMPv1 de leitura e clique em **Salvar configurações** e **Testar conexão**.

O App não exige edição de `configuration.yaml`, não depende de Wi-Fi ou nuvem e não publica portas na LAN. O broker MQTT é descoberto automaticamente quando oferecido pelo Supervisor; também é possível informar um broker manual no painel.

## Estado da implementação

- SNMPv1: GET e WALK somente leitura, com descoberta dinâmica de consumíveis.
- EWS: GET somente leitura da página principal, com indicação de fonte e disponibilidade.
- MQTT Discovery: dispositivo único com identificadores estáveis e disponibilidade separada do App.
- IP vazio: painel funcional, monitoramento suspenso e nenhuma entidade de impressora criada.
- Reboot: teste manual e supervisionado, bloqueado se `prtGeneralReset` não responder por GET; nenhum retry e nenhum reset destrutivo.
- Wake: indisponível; Wake-on-LAN não é presumido.

Leia [`tecnohead_hp/README.md`](tecnohead_hp/README.md), [`tecnohead_hp/DOCS.md`](tecnohead_hp/DOCS.md) e [`docs/RELATORIO_CAPACIDADES.md`](docs/RELATORIO_CAPACIDADES.md) para detalhes, segurança, rollback e limitações.

## Desenvolvimento local

```bash
python -m unittest discover -s tests -t . -v
```

O projeto usa Dockerfile moderno e não contém `build.yaml` legado.
