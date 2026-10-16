# Documentação do TecnoHead HP

## Pré-requisitos

- Home Assistant OS com o App MQTT/Mosquitto configurado ou um broker MQTT acessível na LAN.
- HP Color LaserJet Pro MFP M176n conectada por Ethernet.
- IP obtido no painel da impressora em `Setup → Network Setup → Show IP Address`.
- Comunidade SNMPv1 de leitura conhecida pelo administrador.
- Comunidade SNMPv1 de escrita separada somente se for realizar a homologação do reboot.

## Configuração pelo Ingress

O primeiro carregamento mostra `Aguardando configuração da impressora`, com o IP vazio. Preencha o endereço, a comunidade SNMP e, se necessário, host/porta/credenciais MQTT. O campo de IP sempre permanece editável, mesmo quando a impressora está offline.

Os botões de diagnóstico fazem somente leituras: SNMP GET/WALK, GET HTTP/EWS e publicação de uma mensagem de teste no broker. O teste normal do reboot exige autorização salva e confirmação do `prtGeneralReset` por GET. O botão separado de envio forçado ignora somente essa confirmação e envia exatamente uma solicitação fixa `powerCycleReset(4)`, sem aguardar resposta posterior e sem retry. O app não aceita OID/valor arbitrário, reset de NVRAM ou reset de fábrica.

## Entidades MQTT

Quando o IP estiver configurado e o broker disponível, o App publica discovery para um dispositivo estável chamado `TecnoHead HP · HP M176n`. As entidades são criadas conforme os dados disponíveis; consumíveis ausentes não viram sensores falsos. A disponibilidade do App e a disponibilidade da impressora são distintas.

O tópico raiz padrão é `tecnohead_hp/printers/m176n_01`. Comandos não são publicados nem assinados na V1.

## Segurança

- Use comunidades SNMP separadas para leitura e, apenas durante o teste autorizado, escrita; ambas são armazenadas em `/data/config.json` com modo restrito e nunca retornam pela API.
- SNMPv1 e HTTP não cifram o tráfego. Mantenha a impressora e o App em uma LAN/VLAN confiável.
- Não publique a porta 8099 diretamente. O `config.yaml` usa Ingress; o servidor aceita somente o gateway de Ingress `172.30.32.2` em produção.
- Diagnósticos mascaram credenciais e não incluem o conteúdo completo da página EWS.

## Backup, atualização e rollback

O diretório `/data` é persistente e deve entrar no backup do Home Assistant. Antes de atualizar, faça um backup completo. Para rollback, instale a tag anterior no repositório e restaure o backup do App se necessário. A configuração não exige reinstalação para troca do IP.

## Limitações homologadas

Na unidade real atual, o OID `prtGeneralReset` não foi confirmado por GET, portanto o teste normal permanece bloqueado. O teste forçado pode ser usado com acesso físico disponível, comunidade SNMP de escrita e autorização salva; ele não garante que o firmware aceite o comando. Wake-on-LAN não é presumido.
