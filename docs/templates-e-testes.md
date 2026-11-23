# Onde ficam os templates, scripts e ensaios

Este índice identifica o código da plataforma que prepara e modifica o clone local NASA e o protocolo que produz os resultados da avaliação técnica. As fontes NASA são baixadas pelo instalador; não estão incluídas neste repositório.

## Instalação e integração da missão

| Operação | Entrada pública | Implementação e material usado |
| --- | --- | --- |
| Baixar a revisão NASA e seus submódulos | `./start --no-ui source install` | [`project/nasa_source.py`](../project/nasa_source.py), chamado por [`scripts/install-cfs.sh`](../scripts/install-cfs.sh). |
| Preparar os caminhos e definições locais | Preparação da missão | [`project/flight_sources.py`](../project/flight_sources.py); copia as definições oficiais e cria os aliases para `cFS/apps` e `cFS/libs`. |
| Criar app | `./start --no-ui app new NOME` | [`project/appgen/sample.py`](../project/appgen/sample.py) lê `cFS/apps/sample_app`; [`project/appgen/render.py`](../project/appgen/render.py) aplica os [templates](../project/appgen/templates). A dependência `sample_lib` permanece separada. |
| Criar biblioteca | `./start --no-ui library new NOME` | `library_sources` em [`project/appgen/sample.py`](../project/appgen/sample.py) lê `cFS/libs/sample_lib`. |
| Adicionar comandos, leitores e telemetria | `./start --no-ui project --help` | [`project/manage.py`](../project/manage.py), [`project/appgen/appgen.py`](../project/appgen/appgen.py) e [templates de integração HAL](../project/appgen/templates/hal_sensor). |
| Escolher modelo e transporte do sensor | Vínculo do dispositivo no projeto | [Catálogo de modelos e drivers](../project/drivers/README.md), com os registradores e conversões em [`project/drivers/models`](../project/drivers/models). |
| Incluir/retirar módulo da missão | `app add/remove`, `library add/remove` | [`project/mission_config.py`](../project/mission_config.py); retirada preserva os fontes. |
| Renomear ou excluir módulo próprio | Operações do workspace/CLI | [`project/module_rename.py`](../project/module_rename.py), [`project/module_delete.py`](../project/module_delete.py) e exclusão de bibliotecas em [`project/mission_config.py`](../project/mission_config.py). |
| Compilar e executar | `./start --no-ui build/run --target ALVO` | [`scripts/build-cfs.sh`](../scripts/build-cfs.sh) e [`hardware/manager.py`](../hardware/manager.py). O padrão de compilação é um job. |
| Descobrir formatos de mensagens e observar respostas | `./start --no-ui ground --help` | [`ground_station/`](../ground_station), com catálogo derivado dos fontes e do build. |

A [auditoria do wrapper](cfs-wrapper.md) explica a separação entre fontes NASA, arquivos gerados e estado da plataforma. O [guia do projeto](../project/README.md) mostra as operações de criação e remoção. O [guia dos templates](../project/appgen/README.md) descreve os trechos gerenciados e os pontos editáveis.

## Avaliação técnica reproduzível

O diretório [`validation/`](../validation) reúne o protocolo da avaliação, os executores sem interface gráfica e a estrutura dos resultados. Seu [README](../validation/README.md) identifica a ordem de execução, os alvos necessários, as repetições e os arquivos brutos de cada questão Q1–Q5.

A avaliação usa uma missão separada, criada pelos scripts da plataforma sobre o clone oficial, e estímulos constantes ou em degraus. Nenhum resultado de órbita ou eclipse integra esse protocolo. Os resultados registram a revisão de código avaliada; uma captura de tela ilustra a telemetria, mas não substitui eventos, pacotes, contadores e resumos criptográficos da medição.

## Testes de desenvolvimento

[`interface/tests/`](../interface/tests) contém testes de regressão de Python, JavaScript e navegador. Esses testes complementam a avaliação técnica; seus cenários simulados não são apresentados como medições de uma placa física. Os arquivos em `interface/tests/fixtures` são exclusivos desses testes.

Uma verificação rápida das proteções de geração pode ser executada com:

```sh
python3 -B -m unittest interface.tests.test_nasa_source interface.tests.test_app_template interface.tests.test_module_rename interface.tests.test_library_delete
```

Os testes JavaScript da interface usam módulos ES no Node:

```sh
node --experimental-default-type=module --test --test-concurrency=1 interface/tests/*.mjs
```

Os executores da avaliação final e seus dados são documentados separadamente para que seja possível localizar a evidência de cada critério sem depender da interface do Studio.
