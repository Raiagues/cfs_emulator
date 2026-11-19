# Revisão do PR 1 de rshz3028

Em 19 de novembro de 2026, o PR estava aberto, com dois commits e seis arquivos alterados. A comparação usou a ponta `3655974523b6`, a base comum `f9b21e76e049` e a revisão `f1cdb0eb8fdf` de `main`. Em um clone temporário, `git merge-tree --write-tree origin/main pr1` identificou conflitos de conteúdo em `boot.sh` e `hardware/manager.py`. As mudanças foram avaliadas sobre o código do Studio em uso. [Pull request 1](https://github.com/Raiagues/cfs_emulator/pull/1)

| Arquivo do PR | Resultado no Studio |
| --- | --- |
| `boot.sh` | Um contêiner encerrado conserva os logs para `./logs.sh`. No próximo boot, o script verifica o estado no Docker, substitui o contêiner encerrado e recusa uma segunda instância ativa. A verificação da versão dos modelos de registradores continua antes do boot. |
| `hardware/manager.py` | A parada de uma placa já comparava destino, porta, usuário e diretório de instalação por meio de `same_board`. Foi acrescentada cobertura de regressão. A execução agora reutiliza a sondagem SSH e verifica a prontidão depois da autorização. Uma placa sem serviço pronto recebe a instrução específica de configuração antes do upload. |
| `hardware/run.py` | O ponto de entrada antigo `python3 -m hardware.run` delega a `./start --no-ui run`. A execução e o acompanhamento de logs seguem um único fluxo. |
| `interface/backend/terminal.py` | Cada leitura copia no máximo 64 KiB a partir do cursor pedido, inclusive quando a janela atravessa blocos. O cursor indica quando a parte antiga da saída já foi descartada. |
| `run.sh` | O atalho chama a CLI principal. A saída inclui o resultado da inicialização e os logs seguintes. |
| `start` | `./start --port 8766` e `./start --ui --port 8766` abrem a mesma interface. A troca de placa ou sistema operacional usa a mesma proteção do setup e da API quando o QEMU está em execução. |

## Retenção de versões na placa

O segundo commit propõe recuperar espaço depois de uma inicialização bem-sucedida. O loop proposto percorre todos os subdiretórios de `releases/`. Uma instalação existente também pode ter dados manuais, links e uploads incompletos nesse diretório. [Segundo commit do PR](https://github.com/Raiagues/cfs_emulator/pull/1/commits/3655974523b6e2879a80da92e40a0256f64c903e)

O ativador do Studio testa o estado do serviço após a partida e marca a versão saudável com `.flight-studio-release`. Ele guarda a versão ativa e a anterior. Somente versões mais antigas com nome válido e marcador correspondente podem ser removidas. Versões antigas sem marcador, diretórios de usuários e links simbólicos ficam preservados. Uma falha na partida restaura o link anterior e mantém o upload para inspeção. [Implementação da ativação](../hardware/activate_release.py)

## Verificação

- O teste HTTP abre uma sessão local, usa a cópia da NASA em um projeto temporário e exercita a proteção de mudança de perfil. Também confere as revisões de fonte e de missão. [Teste de workspace](../interface/tests/test_workspace_http.py)
- Os testes de execução cobrem a janela de bytes do terminal, os dois formatos da opção de porta, a parada em outra placa e a falta de autorização depois da configuração. O teste de retenção usa diretórios e links reais em uma pasta temporária, com respostas de serviço controladas para a partida saudável e a falha. [Testes de execução](../interface/tests/test_execution.py)
- Na verificação local, `./start --port 0` entregou uma sessão HTTP em uma porta efêmera. Um teste de `boot.sh` com respostas controladas de Docker e SSH verificou a recusa com contêiner ativo e a substituição do contêiner encerrado. O teste da política de limpeza rodou em disco temporário.

- No QEMU real, o guest confirmou o boot por SSH e encerrou com código 0. O contêiner encerrado reteve o console para consulta por `docker logs`.
- A missão padrão foi enviada à Raspberry Pi física pelo fluxo atualizado de releases. O serviço entrou em estado operacional, a estação recebeu o evento de resposta ao NOOP e a instalação anterior foi restaurada após o ensaio.

Depois de clonar o cFS pelo setup, o comando abaixo executa a suíte no repositório.

```sh
python3 -m unittest discover -s interface/tests -v
```
