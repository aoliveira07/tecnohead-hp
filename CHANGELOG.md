# Changelog

## [1.0.10] - 2026-10-16

- Adicionado botão de homologação forçada para enviar uma única solicitação fixa `powerCycleReset(4)` sem pré-validar a presença do OID.
- O modo forçado não aceita OIDs/valores arbitrários, não aguarda confirmação e não repete o envio; o resultado deve ser observado pelo retorno e pelo tempo de atividade.

## [1.0.9] - 2026-10-16

- Adicionada homologação supervisionada do `powerCycleReset(4)` via Printer-MIB.
- O teste exige comunidade SNMP de escrita separada, autorização no painel, confirmação do OID por GET e estado ocioso.
- O envio ocorre no máximo uma vez, sem retry; a verificação posterior usa somente GET e nunca permite reset de NVRAM ou de fábrica.
- Na unidade real atual, o OID não foi confirmado, portanto nenhum SNMP SET é enviado.

## [1.0.8] - 2026-10-16

- Adicionado o campo **Tempo de atividade** ao painel, usando o uptime SNMP já coletado.
- Renomeado o sensor MQTT exibido de “Tempo ligada” para “Tempo de atividade”, preservando o identificador existente.

## [1.0.7] - 2026-10-16

- Corrigida a interpretação do byte nulo de flags de erro retornado pela HP como estado sem erro.

## [1.0.6] - 2026-10-16

- Isoladas as consultas SNMP para que um OID opcional não interrompa toda a leitura.
- Tabelas SNMP não suportadas pelo firmware agora são tratadas como indisponíveis.

## [1.0.5] - 2026-10-16

- Corrigida a descoberta automática do broker MQTT pelo Supervisor, que retorna os dados dentro de `data`.
- Testes MQTT agora tratam respostas incompletas sem gerar erro interno no painel.
- Compatibilizado o callback de conexão com os `ReasonCode` do paho-mqtt atual.

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
