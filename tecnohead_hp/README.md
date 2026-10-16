# TecnoHead HP — App Home Assistant OS

O **TecnoHead HP** é um App para Home Assistant OS, não uma integração HACS. Ele acessa a HP Color LaserJet Pro MFP M176n na rede local por cabo Ethernet usando SNMPv1 para leitura e HTTP/EWS opcional para dados complementares.

O endereço IP não é codificado nem exigido na instalação. Abra o painel Ingress, preencha **Endereço IP da impressora**, salve e teste. A alteração de IP interrompe a coleta antiga, descarta o estado volátil anterior e mantém os mesmos identificadores MQTT.

Nenhum comando de escrita é enviado durante inicialização, descoberta, teste de conexão, atualização ou troca de IP. O painel contém uma porta de homologação manual para `powerCycleReset(4)`: ela exige comunidade SNMP de escrita separada, autorização salva, GET positivo do `prtGeneralReset` e estado ocioso. O envio é único e não tem retry; o botão não fica funcional quando o OID não é confirmado. `Acordar` continua indisponível.

O painel e o MQTT Discovery exibem o `sysUpTime.0` como **Tempo de atividade**, isto é, o tempo desde a última inicialização observada do sistema de gerenciamento da impressora.
