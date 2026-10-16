# Documentação do TecnoHead HP

## Pré-requisitos

- Home Assistant OS com o App MQTT/Mosquitto configurado ou um broker MQTT acessível na LAN.
- HP Color LaserJet Pro MFP M176n conectada por Ethernet.
- IP obtido no painel da impressora em `Setup → Network Setup → Show IP Address`.
- Comunidade SNMPv1 de leitura conhecida pelo administrador.

## Configuração pelo Ingress

O primeiro carregamento mostra `Aguardando configuração da impressora`, com o IP vazio. Preencha o endereço, a comunidade SNMP e, se necessário, host/porta/credenciais MQTT. O campo de IP sempre permanece editável, mesmo quando a impressora está offline.

Os botões de diagnóstico fazem somente leituras: SNMP GET/WALK, GET HTTP/EWS e publicação de uma mensagem de teste no broker. Eles não fazem `SNMP SET`, POST administrativo, impressão, wake ou reboot.

## Entidades MQTT

Quando o IP estiver configurado e o broker disponível, o App publica discovery para um dispositivo estável chamado `TecnoHead HP · HP M176n`. As entidades são criadas conforme os dados disponíveis; consumíveis ausentes não viram sensores falsos. A disponibilidade do App e a disponibilidade da impressora são distintas.

O tópico raiz padrão é `tecnohead_hp/printers/m176n_01`. Comandos não são publicados nem assinados na V1.

## Segurança

- Use comunidade SNMP somente leitura; ela é armazenada em `/data/config.json` com modo restrito e nunca retorna pela API.
- SNMPv1 e HTTP não cifram o tráfego. Mantenha a impressora e o App em uma LAN/VLAN confiável.
- Não publique a porta 8099 diretamente. O `config.yaml` usa Ingress; o servidor aceita somente o gateway de Ingress `172.30.32.2` em produção.
- Diagnósticos mascaram credenciais e não incluem o conteúdo completo da página EWS.

## Backup, atualização e rollback

O diretório `/data` é persistente e deve entrar no backup do Home Assistant. Antes de atualizar, faça um backup completo. Para rollback, instale a tag anterior no repositório e restaure o backup do App se necessário. A configuração não exige reinstalação para troca do IP.

## Limitações homologadas

Sem acesso à unidade física, os valores de uptime, estado, erros, EWS, níveis, firmware e contador de páginas permanecem pendentes. O OID `prtGeneralReset` é consultável apenas como GET durante diagnóstico, mas reboot não é implementado nem exposto. Wake-on-LAN não é presumido.
