# TecnoHead HP — App Home Assistant OS

O **TecnoHead HP** é um App para Home Assistant OS, não uma integração HACS. Ele acessa a HP Color LaserJet Pro MFP M176n na rede local por cabo Ethernet usando SNMPv1 somente para leitura.

O endereço IP não é codificado nem exigido na instalação. Abra o painel Ingress, na aba **Configurações**, preencha o nome, o IP e a comunidade SNMPv1 de leitura, salve e teste. A alteração de IP interrompe a coleta antiga, descarta o estado volátil anterior e mantém os mesmos identificadores MQTT.

O App opera em modo somente leitura para a impressora: não envia comandos SNMP SET, não oferece reinício remoto, reset de fábrica ou sondagem de OIDs de escrita. Os diagnósticos consultam somente SNMP GET/WALK e o MQTT do próprio Home Assistant.

Opcionalmente, a mesma aba permite informar uma entidade do Sonoff com Tasmota e um horário diário. Nesse horário o App chama `homeassistant.turn_off` pela API interna do Home Assistant. O Tasmota deve estar configurado para religar o Sonoff sozinho; o App não envia comando de ligar.

O painel e o MQTT Discovery exibem o `sysUpTime.0` como **Tempo de atividade**, isto é, o tempo desde a última inicialização observada do sistema de gerenciamento da impressora.
