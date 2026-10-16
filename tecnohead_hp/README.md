# TecnoHead HP — App Home Assistant OS

O **TecnoHead HP** é um App para Home Assistant OS, não uma integração HACS. Ele acessa a HP Color LaserJet Pro MFP M176n na rede local por cabo Ethernet usando SNMPv1 para leitura e HTTP/EWS opcional para dados complementares.

O endereço IP não é codificado nem exigido na instalação. Abra o painel Ingress, preencha **Endereço IP da impressora**, salve e teste. A alteração de IP interrompe a coleta antiga, descarta o estado volátil anterior e mantém os mesmos identificadores MQTT.

Nenhum comando de escrita é enviado durante inicialização, descoberta, teste de conexão, atualização ou troca de IP. O painel contém um **Laboratório de comandos SNMP**: ele lista o `prtGeneralReset.1`, mostra os valores padronizados 3–6, permite sondar o Printer-MIB e a raiz privada HP somente com GET/GETNEXT e oferece envio direto de `powerCycleReset(4)`, `resetToNVRAM(5)` e `resetToFactoryDefaults(6)`. Cada botão faz um único SET e mostra o retorno SNMP imediato; não faz pré-GET, não espera o reboot, não verifica uptime, não faz retry e não aplica cooldown. Há também um botão para tentar os três valores em sequência imediata. O App não aceita OIDs arbitrários: a descoberta privada HP é informativa, pois nenhum reboot específico da M176n foi confirmado. A opção 6 pode exigir reconfiguração física após o envio. `Acordar` continua indisponível.

O painel e o MQTT Discovery exibem o `sysUpTime.0` como **Tempo de atividade**, isto é, o tempo desde a última inicialização observada do sistema de gerenciamento da impressora.
