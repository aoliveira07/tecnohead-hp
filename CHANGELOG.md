# Changelog

## [1.0.3] - 2026-10-16

- Corrigida a expressão regular do caminho relativo da API do Ingress; o JavaScript do formulário volta a carregar e impedir o envio GET acidental.

## [1.0.2] - 2026-10-16

- Corrigida a API do painel Ingress para usar caminhos relativos; o painel não tenta mais acessar `/api/*` na raiz do Home Assistant.

## [1.0.1] - 2026-10-16

- Adicionada validação CI dos testes, sintaxe e build do container.

## [1.0.0] - 2026-10-16

- Primeira versão do App TecnoHead HP.
- Painel Ingress em pt-BR com IP vazio na instalação, persistência e teste de conexão.
- Sondagem SNMPv1 somente leitura para estado, uptime, erros e suprimentos.
- Consulta EWS somente leitura e indicação da origem dos dados.
- MQTT Discovery com disponibilidade e identificadores estáveis.
- Reboot e wake mantidos não homologados e não funcionais.
