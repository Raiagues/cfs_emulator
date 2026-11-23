# Auditoria do wrapper cFS — 23/11/2026

Escopo: checkout `boot_cfs-estudio`, branch `recuperacao/estudio-cfs`. A auditoria verifica a origem dos fontes, o provisionamento, a geração de módulos e a proteção das edições locais. Não migra a missão existente nem modifica os arquivos originais NASA.

## Resultado

A base funciona como um wrapper sobre um clone oficial local. A árvore versionada atual da plataforma não contém `cFS/` nem módulos gerados do workspace. A configuração versionada começa com `apps`, `devices` e `buses` vazios, sem placa ou sistema escolhido. Os exemplos e serviços que já fazem parte da distribuição NASA continuam presentes: “vazio” significa sem apps ou sensores próprios da plataforma.

Há duas diferenças em relação ao fluxo solicitado: o download atualmente é uma ação explícita **Source** na preparação, e as definições da missão ficam fora do clone. Não foi feita uma migração automática para alterar essas decisões nesta auditoria.

## Origem e preparação

1. `./start` abre o Studio; selecionar um target grava a escolha e verifica pré-requisitos.
2. Se o código NASA estiver ausente, a preparação solicita **Source**. Essa ação chama `scripts/install-cfs.sh` e `./start --no-ui source install`.
3. `project/nasa_source.py` clona `https://github.com/nasa/cFS.git` em uma pasta temporária, seleciona a revisão `a4d305dc06fb7d468f5b45214d9f730b97d4bd77`, inicializa os submódulos e só então disponibiliza o diretório `cFS/`. A atualização de submódulos usa um job.
4. `project/flight_sources.py` prepara os caminhos locais e copia as definições oficiais para a missão. Não instala HALs nem apps próprias nessa etapa.
5. O build usa esse clone. Native usa o compilador local. Emulator e Board usam o container de compilação cruzada, com `cFS/` montado somente para leitura durante o build. Os módulos compilados são transferidos ao destino na execução.

Criar a imagem Docker não clona automaticamente o cFS. A imagem do emulador contém o ambiente Linux/QEMU, não uma missão cFS pronta. Native não exige uma imagem Docker. Os destinos usam a mesma base local; não há um clone independente dentro de cada target.

O checkout inspecionado tem a origem oficial, está na revisão fixada, tem 24 submódulos nas revisões registradas e não apresenta alterações locais. O conjunto de arquivos versionados da plataforma sob `cFS/`, `mission/`, `project/apps/` e `project/generated/` está vazio. O `.dockerignore` também exclui essas fontes locais do contexto da imagem.

## Caminhos e propriedade

| Caminho | Papel |
| --- | --- |
| `cFS/` | Clone oficial local, independente do Git da plataforma. |
| `cFS/apps/<nome>/` | Fontes de uma app adicionada pelos scripts, ao lado dos módulos oficiais. |
| `cFS/libs/<nome>/` | Fontes de uma biblioteca adicionada pelos scripts. |
| `mission/apps`, `mission/libs` | Aliases relativos para `../cFS/apps` e `../cFS/libs` em missões novas. |
| `mission/sample_defs/` | Definições copiadas da NASA e adaptadas pelos scripts; o original `cFS/sample_defs/` permanece preservado. |
| `mission/cpu1_cfe_es_startup.scr`, `mission/modules.cmake`, `mission/libraries.cmake` | Inicialização e seleção de módulos gerenciadas pela plataforma. |
| `mission/build-native/`, `mission/build-flight/` | Saídas de compilação locais. |
| `project/`, `scripts/` | Implementação dos geradores, templates, validação e operações. |
| `project/apps/`, `project/generated/` | Manifestos e registros gerados no workspace; ignorados pelo Git da plataforma. |

Os aliases foram confirmados no workspace atual. Missões antigas que já tenham diretórios reais em `mission/apps` ou `mission/libs` são preservadas pelo preparador; não são movidas silenciosamente para o clone. Portanto, manter *todos* os arquivos da missão dentro de `cFS/` exigiria outra alteração de arquitetura.

## Criação a partir dos exemplos oficiais

`project/appgen/sample.py::copy_sample` lê os arquivos do exemplo instalado naquele clone, em `cFS/apps/sample_app` ou `cFS/libs/sample_lib`. O gerador não usa uma app completa própria como base para as novas apps de schema 2.

A criação de uma app renomeia os identificadores de `sample_app` e preserva a biblioteca `sample_lib`: seu include, `SAMPLE_LIB_Function` e a dependência CMake continuam apontando para a biblioteca oficial. Criar uma biblioteca é uma operação separada, derivada de `sample_lib`.

`extend_app` aplica os templates e pontos de integração da plataforma à cópia: CMake, identificadores, despacho de comandos, wakeups e arquivos auxiliares. Os scripts de missão integram a seleção de módulos, o startup e as tabelas. Os nomes de módulos NASA são protegidos nas operações de escrita e exclusão.

Uma nova app já recebe arquivos auxiliares de componentes/user e pontos de integração para sensores, mesmo sem sensor configurado. Isso é código gerado pelos templates, não uma HAL pré-instalada na missão vazia; ainda assim, não é uma cópia mínima com apenas troca de nome. Os templates antigos de schema 1 permanecem para compatibilidade com projetos anteriores.

Há fontes completos em `interface/tests/fixtures/bancada/`. São dados de testes isolados, não fontes instalados no primeiro boot nem conteúdo da imagem Docker. Os drivers compartilhados em `project/drivers/` também ficam fora do clone e são materializados conforme as dependências escolhidas. Esses diretórios não foram apagados nesta auditoria.

## Correções de proteção

- O Git agora ignora toda a missão local, os manifestos de apps e os artefatos gerados. Antes, alguns arquivos materializados, como startup e seleção de módulos, ainda podiam aparecer para commit.
- A sincronização compara os blocos CMake gerenciados com o manifesto anterior. Uma edição manual dentro desses blocos interrompe o plano antes da gravação, em vez de ser sobrescrita. Entradas externas aos blocos e a dependência `sample_lib` são preservadas.
- A exclusão de uma biblioteca verifica também os consumidores arquivados, inclusive referências CMake, includes e chamadas. A árvore inteira é guardada temporariamente até a validação da missão; em caso de erro, ela é restaurada. Diretórios vazios não ficam bloqueando a reutilização do nome. Retirar uma biblioteca da missão continua preservando os fontes.
- O resultado da preparação informa o HEAD realmente instalado e a revisão base NASA separadamente; uma extensão local aceita não é mais reportada como se ainda fosse exatamente o commit base.

Nenhum arquivo da configuração atual do usuário foi incluído nessas alterações. Não houve alteração de sensores, criação de apps no workspace real, substituição do clone ou publicação no GitHub.

## Evidências e limites

Os testes unitários de origem NASA, templates, renomeação e exclusão de bibliotecas passaram: 23 testes. Cobrem também a interrupção sem gravações parciais diante de mudanças manuais no CMake, a idempotência, a preservação de `sample_lib`, o bloqueio de referências arquivadas e a restauração de arquivos binários, permissões e diretórios vazios quando a exclusão falha.

Na cópia isolada, APIs reais e a CLI validaram criar, renomear, retirar da missão, recolocar e excluir uma app; também validaram criar, retirar, recolocar e excluir uma biblioteca padrão. A verificação confirmou a preservação de 4.461 arquivos oficiais rastreados, da configuração real e dos diretórios de apps reais. O ciclo reproduziu separadamente a falha de exclusão diante de diretórios vazios preexistentes, registrada em `lifecycle-before-fix.json`.

Após as correções, o ciclo completo passou com 29 etapas e nenhum problema pendente nessa execução. Incluiu exclusão e recriação do mesmo nome de biblioteca, dependência de app arquivada, restauração dessa app e rollback após falha injetada de validação. O resultado está em `lifecycle-after-fix.json`; o roteiro local está em `validate-lifecycle-after-fix.py`. Esses arquivos registram a cópia temporária usada e não devem ser executados contra a missão real.

O registro local da origem, revisões, aliases e configuração distribuída está em `hardware/.runtime/validation/wrapper-2026-11-23/workspace.json`. Essa pasta de evidências é ignorada pelo Git.

Esta auditoria não repetiu um download pela rede, build Docker ou execução em Raspberry Pi física. A inspeção do provisionamento e os testes de geração não devem ser apresentados como validação de execução nos três targets.
