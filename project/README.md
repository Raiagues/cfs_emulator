# Projeto e missão

A NASA fornece o framework, as apps padrão e os exemplos em um checkout independente, `cFS/`. O Studio cria o software da missão em `mission/` e guarda as escolhas da pessoa em `project/`. Para baixar o upstream e abrir o primeiro workspace, siga o [guia inicial](../README.md).

Ao preparar uma missão, o Studio usa os arquivos oficiais de `cFS/sample_defs/` para inicializar as definições locais. O build recebe `mission/sample_defs/` em `MISSION_DEFS` e procura módulos nos diretórios da NASA e da missão usando `CFS_APP_PATH`. O Git do Studio ignora o checkout da NASA, as definições locais materializadas e os diretórios de compilação. Apps próprias, bibliotecas, mapas de sensores e configurações da missão ficam disponíveis para versionamento.

```mermaid
flowchart LR
    A["App baseada em sample_app"] --> C["CMake e startup da CPU1"]
    L["Biblioteca baseada em sample_lib"] --> C
    A --> SCH["Agendamento SCH_LAB"]
    A --> TO["Inscrições TO_LAB"]
    C --> B["Build cFS"]
    SCH --> B
    TO --> B
```

## Aplicações e bibliotecas

Na arquitetura 2D, **New** cria ou inclui um módulo no grupo selecionado. Para uma app própria, o rascunho mostra ponto de entrada, prioridade, pilha, frequência de wakeup e frequência de housekeeping. Salvar aplica as definições ao build e ao startup. Os quatro comandos padrão da cópia de `sample_app` continuam disponíveis. [Navegação e ações no workspace](../interface/README.md#editar-a-missão)

```sh
./start --no-ui app new attitude_app --priority 60 --stack-size 32768 --wakeup-hz 2 --hk-hz 0.25 --preview
./start --no-ui app new attitude_app --priority 60 --stack-size 32768 --wakeup-hz 2 --hk-hz 0.25
./start --no-ui app edit attitude_app --wakeup-hz 1
./start --no-ui library new payload_lib --preview
./start --no-ui library new payload_lib
```

| Operação | Efeito |
| --- | --- |
| **Edit → Rename module** | Renomeia um módulo próprio e atualiza arquivos, símbolos, referências, CMake e startup. Os identificadores dos módulos oficiais permanecem os da NASA. |
| `app disable` / `app enable` | Controla a inicialização da app incluída no build. |
| `app remove` / `library remove` | Retira o módulo da missão e preserva os fontes para uma inclusão futura. |
| `app add` / `library add` | Inclui um módulo existente e suas dependências. |
| `app delete` / `library delete` | Exclui os fontes de um módulo próprio. Um módulo ainda usado por outro precisa ter essa dependência resolvida antes da exclusão. |
| `app list` / `library list` | Mostra a seleção de apps ou as bibliotecas disponíveis. |

Essas operações de CLI recebem o prefixo `./start --no-ui`. Por exemplo, `./start --no-ui app remove attitude_app` retira a app da missão e `./start --no-ui app add attitude_app` volta a incluí-la. A CLI e o navegador usam a mesma implementação. Uma falha de gravação restaura os arquivos da transação.

As apps de missão mantêm handlers, payloads e lógica periódica editáveis. O gerador usa marcadores nos trechos de integração do `sample_app` para preservar a implementação manual nas sincronizações seguintes. A biblioteca gerada a partir de `sample_lib` oferece as pastas `fsw/src/` e `fsw/public_inc/`. [Templates e pontos de edição](appgen/README.md)

## Vincular um sensor e enviar telemetria

O perfil Raspberry Pi disponibiliza o barramento I²C. O exemplo abaixo utiliza `attitude_app`, criada acima, e um TMP105 no endereço 0x49. Em uma placa física, escolha o endereço de sete bits do seu dispositivo.

```sh
./start --no-ui profile --board raspi4b --os raspios
./start --no-ui project add-bus i2c-bus.1
./start --no-ui project add-device "Payload temperature" --id payload_temp --model tmp105 --bus i2c-bus.1 --address 0x49 --value temperature=27000
./start --no-ui project add-sensor attitude_app board_temp --device payload_temp
./start --no-ui project add-command attitude_app set_mode
./start --no-ui project add-telemetry attitude_app temperature --sensor board_temp
./start --no-ui project locate attitude_app
```

Em **Hardware**, selecione **Add bus**, escolha o conector da placa e use **Add sensor** para definir modelo e endereço. Ao clicar no sensor, **Link HAL** permite escolher uma app de missão ou criar uma a partir de `sample_app`. O código C do leitor fica acessível no vínculo. Na CLI, `link-hal science temperature --device payload_temp --new-app` cria a app e o leitor na mesma operação. Para usar uma app existente, omita `--new-app`.

`add-device` cria uma instância com ID, barramento e endereço. `add-sensor` vincula um leitor daquela app à instância. `add-command` cria a estrutura da mensagem e um handler para implementar. `add-telemetry --sensor` prepara o pacote com dados, status e validade do leitor. `locate` informa o caminho e a linha de cada ponto editável. A remoção de um leitor e a remoção do dispositivo físico são operações distintas.

A biblioteca do chip usa `hal_sensor`. O leitor associa o dispositivo ao transporte informado pela placa. Leitores vinculados e dependências CMake determinam quais bibliotecas entram no build e em que ordem o cFE as carrega. Para um chip novo, registre uma definição em **Hardware** ou use `./start --no-ui project register-model <arquivo>`. [Modelos, barramentos e HAL](drivers/README.md)

## Mapa dos arquivos

| Arquivo | Responsabilidade |
| --- | --- |
| `project/config.json` | Placa e SO selecionados, dispositivos e vínculos com módulos de missão |
| `project/apps/<app>.json` | MIDs, desempenho, agendamento, comandos, leitores e telemetria da app |
| `project/boards/<placa>.json` | Perfil de build, sistemas, barramentos e catálogo da placa |
| `project/drivers/models/<id>/model.json` | Identidade, registradores, conversões, canais e ABI do sensor |
| `project/drivers/catalog.json` | HAL e transportes compartilhados |
| `project/generated/drivers.json` | Assinaturas dos arquivos materializados para preservar edições locais |
| `mission/apps/`, `mission/libs/` | Fontes compilados dos módulos da missão |
| `mission/modules.cmake`, `mission/libraries.cmake` | Seleção própria de módulos da CPU1 e bibliotecas da missão |
| `mission/cpu1_cfe_es_startup.scr` | Módulos ativos e receitas arquivadas de inicialização |
| `mission/sample_defs/targets.cmake` | Listas de módulos por CPU |
| `mission/sample_defs/toolchain-<arquitetura>.cmake` | Toolchain para o perfil ativo |
| `mission/sample_defs/default_osconfig.cmake`, `cfe_core_api_interface_cfg_values.h` na mesma pasta | Limites do carregador, nomes de módulos e campos correspondentes no cFE |
| `mission/sample_defs/generate_startup.cmake`, `cpu1/install_custom.cmake` sob `sample_defs/` | Instalação do startup e das tabelas da missão |
| `mission/sample_defs/tables/`, `mission/sample_defs/generated/` | Tabelas de SCH_LAB/TO_LAB e fragmentos de integração gerados |

## Conferir e compilar

```sh
./start --no-ui project list
./start --no-ui project check
./start --no-ui project sync
./start --no-ui build --target qemu
```

`check` informa diferenças e retorna código 1 se houver alterações geradas pendentes. `sync` aplica essas alterações. Depois de modificar fontes ou membros da missão, compile e execute a nova versão no destino desejado. Para alterar dispositivos, endereços ou barramentos emulados, reinicie o QEMU para carregar a topologia. Os ajustes de sinal sintético podem ser aplicados na sessão de dados. [Execução por destino](../hardware/README.md)
