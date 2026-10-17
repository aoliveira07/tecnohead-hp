# Documentação do TecnoHead HP

## Pré-requisitos

- Home Assistant OS com o App MQTT/Mosquitto configurado ou um broker MQTT acessível na LAN.
- HP Color LaserJet Pro MFP M176n conectada por Ethernet.
- IP obtido no painel da impressora em `Setup → Network Setup → Show IP Address`.
- Comunidade SNMPv1 de leitura conhecida pelo administrador.

## Configuração pelo Ingress

O primeiro carregamento mostra `Aguardando configuração da impressora`, com o IP vazio. Na aba **Configurações**, preencha o nome amigável, o endereço IP e a comunidade SNMPv1 de leitura. O campo de IP sempre permanece editável, mesmo quando a impressora está offline.

Os botões de diagnóstico fazem somente leituras: teste de conexão da impressora e SNMP GET/WALK. O App não envia SNMP SET, não sonda OIDs de escrita e não oferece comandos de reinício ou restauração de fábrica.

### Sonoff/Tasmota

Na mesma aba, informe opcionalmente a entidade do Sonoff (por exemplo, `switch.sonoff_impressora`) e o horário diário do comando OFF. Quando os dois campos estiverem preenchidos, o App chama a API interna do Home Assistant uma vez por dia. O religamento deve ser configurado no firmware Tasmota; o App não envia comando ON.

## Entidades MQTT

Quando o IP estiver configurado e o broker do Home Assistant estiver disponível, o App publica discovery para um dispositivo estável chamado `TecnoHead HP · HP M176n`. As entidades são criadas conforme os dados disponíveis; consumíveis ausentes não viram sensores falsos. A disponibilidade do App e a disponibilidade da impressora são distintas.

O tópico raiz padrão é `tecnohead_hp/printers/m176n_01`. Comandos da impressora não são publicados nem assinados na V1.

## Segurança

- A comunidade SNMPv1 de leitura é armazenada em `/data/config.json` com modo restrito e nunca retorna pela API.
- SNMPv1 e HTTP não cifram o tráfego. Mantenha a impressora e o App em uma LAN/VLAN confiável.
- Não publique a porta 8099 diretamente. O `config.yaml` usa Ingress; o servidor aceita somente o gateway de Ingress `172.30.32.2` em produção.
- Diagnósticos mascaram a comunidade SNMP e não incluem credenciais.

## Backup, atualização e rollback

O diretório `/data` é persistente e deve entrar no backup do Home Assistant. Antes de atualizar, faça um backup completo. Para rollback, instale a tag anterior no repositório e restaure o backup do App se necessário. A configuração não exige reinstalação para troca do IP.

## Limitações homologadas

O App não controla a impressora por escrita nem a reinicia diretamente. O tempo de atividade é exibido a partir do `sysUpTime.0`. A rotina opcional atua somente no Sonoff/Tasmota configurado, enviando OFF pelo Home Assistant; o religamento depende do firmware Tasmota.
