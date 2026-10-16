# TecnoHead HP — App Home Assistant OS

O **TecnoHead HP** é um App para Home Assistant OS, não uma integração HACS. Ele acessa a HP Color LaserJet Pro MFP M176n na rede local por cabo Ethernet usando SNMPv1 para leitura e HTTP/EWS opcional para dados complementares.

O endereço IP não é codificado nem exigido na instalação. Abra o painel Ingress, preencha **Endereço IP da impressora**, salve e teste. A alteração de IP interrompe a coleta antiga, descarta o estado volátil anterior e mantém os mesmos identificadores MQTT.

Nenhum comando de escrita é enviado durante inicialização, descoberta, teste, atualização ou troca de IP. `Reiniciar` e `Acordar` não são entidades na V1 porque ainda não foram comprovados na impressora real.
