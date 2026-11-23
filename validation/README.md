# Avaliação técnica final

Este protocolo executa o backend sem navegador. Cada resultado deve vir de uma execução nova, com o commit da plataforma congelado, checkout oficial NASA identificado e uma missão independente. Os testes unitários verificam o harness; seus dados temporários não são resultados do estudo.

O harness só altera missões com `.evaluation.json`, criadas por `prepare`. Não copie a missão ou os artefatos de uma execução anterior. Todos os builds usam um job. Cada diretório de saída deve ser novo; uma falha preserva a evidência parcial e retorna erro, sem completar contagens artificialmente.

## Questões e critérios

| Questão | Procedimento final | Critério |
| --- | --- | --- |
| Q1 | Três repetições NOOP → RESET_COUNTERS → NOOP para `sample_app`, `eval_temp`, `eval_mag`, `eval_mpu`, em cada alvo. | Cada comando recebe EVS da app e housekeeping posterior com sequência distinta. NOOP incrementa CommandCounter; RESET zera contadores; NOOP seguinte produz 1. A emissão UDP isolada não confirma execução. São 36 comandos por alvo. |
| Q2 | Três constantes/patamares por sensor, cinco pacotes distintos por patamar em Native/QEMU. HAL C com constantes e degraus em registradores em memória, três repetições de 15 leituras por cenário e sensor. | Diferença dentro da quantização do modelo e arredondamento da saída; entrada, registradores raw, telemetria e unidades preservados. |
| Q3 | HAL C: cinco leituras válidas, cinco interrupções, cinco recuperadas; três repetições por sensor. Native cFS: indisponibilizar apenas o arquivo de registradores do sensor da missão isolada, coletar cinco inválidas e restaurá-lo. | Status não zero e leitura não válida durante ausência; primeira leitura do HAL após restabelecimento válida. No Native, registrar todos os pacotes recebidos após restauração até a primeira amostra válida, limitada pelo timeout explícito. Na placa, sensor presente válido e sensores ausentes inválidos. |
| Q4 | Um build ARM usado em QEMU e placa; hash por arquivo local e instalado. | Identidade por arquivo e mesmo fingerprint, com qualquer diferença declarada. O executável Native não é comparado ao ARM como binário idêntico. |
| Q5 | Dez ciclos criar app/compilar incrementalmente/excluir no Native; dez inícios cFS por alvo; cinco boots completos do guest QEMU. Builds completos Native e ARM: N=1 cada. | Medidas descritivas: N, mediana, IQR inclusivo, mínimo e máximo. Sem inferência de ganho estatístico ou generalização. |

A aquisição física usa o MPU6050 informado pela operadora como parado no chão. A orientação não é controlada. As medidas são descritivas, sem calibração ou comparação de exatidão com o QEMU. TMP105 e magnetômetro ausentes devem continuar respondendo aos comandos enquanto sinalizam leitura inválida.

Não há órbita, eclipse nem interpretação dinâmica espacial. `protocol.py` fixa os níveis antes da coleta: TMP105 aproximadamente −3 a 32 °C, campo magnético em dezenas de µT, aceleração próxima de 1 g em diferentes vetores e pequenas velocidades angulares. Esses níveis sintéticos não pretendem reproduzir a orientação da bancada física.

## Preparação e registradores

Execute na revisão final commitada. `prepare` usa `git archive HEAD` e o instalador público NASA, depois os comandos públicos de perfil, barramento, sensor, app e HAL. Os diretórios `cFS/` e `mission/` da cópia não são publicados.

```sh
python3 -B -m validation prepare --directory /tmp/flight-evaluation-final
python3 -B -m validation registers \
  --workspace /tmp/flight-evaluation-final/flight \
  --output /tmp/flight-evaluation-final/registers
```

Opcionalmente, `prepare --source-copy /caminho/cFS` faz uma cópia independente de um checkout oficial limpo já disponível. Nesse caso, o relatório declara que não houve novo download de rede. Não use essa opção para alegar validação da instalação pela rede.

O ensaio de registradores compila o HAL C da plataforma e o adaptador de barramento em memória. São 27 execuções e 405 leituras, incluindo 45 leituras durante nove episódios de interrupção programada. Os 256 bytes raw de cada amostra, o status e a leitura efetiva são gravados; um erro não é apresentado como valor válido. O compilador, fontes e modelos têm versão ou hash registrado. O índice de amostra não é um tempo real medido.

## Execução coordenada dos alvos

Antes de iniciar, configure no runtime privado da cópia o acesso SSH autorizado e a imagem QEMU disponível. Nunca publique chaves, tokens ou o dicionário de conexão. Pare a missão de uso normal antes da avaliação. Um operador deve coordenar estes comandos sequencialmente; o harness não remove contêineres nem processos estranhos.

```sh
python3 -B -m validation build --workspace /tmp/flight-evaluation-final/flight \
  --output /tmp/flight-evaluation-final/build-native --target native
python3 -B -m validation cycles --workspace /tmp/flight-evaluation-final/flight \
  --output /tmp/flight-evaluation-final/cycles-native
python3 -B -m validation starts --workspace /tmp/flight-evaluation-final/flight \
  --output /tmp/flight-evaluation-final/starts-native --target native --leave-running
python3 -B -m validation target --workspace /tmp/flight-evaluation-final/flight \
  --output /tmp/flight-evaluation-final/native --target native
```

O comando `target` coleta de uma missão já em operação; não compila nem inicia cFS. Ao terminar, encerra apenas sua conexão de Ground Station. Pare a missão com o `start --no-ui stop --target native` da **cópia** antes do próximo alvo.

Antes de medir o build ARM, prepare a imagem `cfs-builder` definida no Dockerfile e registre seu comando, duração e identificador em `setup-builder/`. O compilador já deve estar disponível, assim como no build Native; o cache-check de imagem executado pelo produto continua dentro da medida de build. Compile ARM uma vez com `validation build --target qemu`. Prepare imagem/disco/SSH uma vez, registrando os identificadores efetivos. A imagem QEMU deve conter o fingerprint de modelos exigido por `project/qemu/generate.py --fingerprint`; sua preparação é um pré-requisito, registrado separadamente em `setup-qemu-image/`, e não uma das cinco medidas de boot. `validation boots --target qemu --leave-running` mede cinco boots do guest previamente desligado, com o mesmo disco persistente e a mesma imagem. Registre separadamente o primeiro boot que provisiona disco, caso ainda não tenha ocorrido; ele não é intercambiável com os cinco boots de disco preparado.

Depois de parar cFS sem desligar o guest, `validation starts --target qemu --leave-running` mede dez starts; `validation target --target qemu` coleta comandos e sensores. Encerre o QEMU antes da placa. A placa reutiliza os artefatos ARM, sem nova compilação: dez `starts --target physical --leave-running` e depois `target --target physical`. Nenhuma fase desliga a placa física.

Cada `run` inclui a transferência/implantação feita pelo produto. O relatório fornece `payload_transfer` separadamente, a primeira linha OPERATIONAL observada (métrica própria), o tempo total de `run` (inclui outras etapas), a conexão/ENABLE_OUTPUT até o primeiro HK e o total até HK. O boot QEMU termina após SSH verificado e a parada do serviço preexistente no guest. Os instantes de log são tempos de observação no host, não timestamps de execução internos do QEMU.

Os dez ciclos incrementais requerem build Native prévio. Depois da décima exclusão, há um build de restauração da missão base, marcado à parte e excluído das dez medidas. Se uma execução exceder recursos/tempo viável, registre a falha e ajuste o protocolo explicitamente antes de repetir; não reduza N silenciosamente.

## Evidências e publicação

Preserve `prepare.json`, `nasa-before.json`, `sources.json`, `commands.json`, logs de build/início, `catalog.json`, `downlink.jsonl`, registros dos sensores/registradores, `artifacts.json` e `metrics.json`. Os pacotes contêm bytes originais, MID, sequência CCSDS, recepção, campos decodificados e erros. Conexões privadas não são serializadas; revise os logs antes de publicar, sem alterar valores, bytes ou tempos medidos.

Somente a campanha concluída deve ir a `validation/results/final/`; tentativas diagnósticas ficam fora dessa pasta. Gere manifesto SHA-256 dos arquivos publicados e registre o commit do harness. O código da NASA, imagens Docker/discos, builds e runtime privado permanecem fora do Git. Uma alteração de código após congelar a revisão exige identificar a nova revisão e repetir a evidência final afetada.

Cada build registra um manifesto das entradas antes da medição. Ao fim dos ciclos incrementais, outro manifesto registra a missão restaurada; o manifesto inicial de prepare não substitui esses registros posteriores.

## Comando de leitura dos registradores

Os dumps remotos usam o mesmo helper público `hardware/sensor_probe.py:READ_REGISTERS`: transações Linux `I2C_RDWR` com repeated START, ponteiro do registrador e leitura do bloco. Cada registro de evidência grava `bus`, `address`, os pares registrador/tamanho e os bytes recebidos. A forma equivalente no terminal, com um alias SSH previamente autorizado, é:

```sh
# Exemplo de argumentos do MPU6050: burst 0x3b/14 bytes, controles e WHO_AM_I.
python3 - "$ALVO_SSH" "$BUS" "$ADDRESS" "$BLOCKS_JSON" <<'PYTHON'
import shlex, subprocess, sys
from hardware.sensor_probe import READ_REGISTERS
command = shlex.join(['python3', '-c', READ_REGISTERS, *sys.argv[2:]])
subprocess.run(['ssh', sys.argv[1], command], check=True)
PYTHON
```

`BUS=1`, `ADDRESS=104` e `BLOCKS_JSON='[[59,14],[107,1],[108,1],[27,1],[28,1],[117,1]]'` identificam o MPU6050 do protocolo. O harness usa os mesmos argumentos, escapados com `shlex.join`; não publica o host ou caminho da chave. Em Native, o dump lê o arquivo `hardware/.runtime/devices/i2c1-0x68.bin` da cópia isolada, que é a imagem de registradores consumida pelo transporte C nativo.

Um dump ausente em Native, QEMU ou no MPU6050 físico reprova o caso; os sensores físicos não conectados podem registrar `unavailable` com erro de I/O. A recuperação Native é limitada a `min(timeout, max(5 s, 3 × período de aquisição + 2 s))`, com período/tabela usados preservados no JSON. O teste registra os pacotes transitórios até o retorno válido. Apenas o ensaio HAL síncrono verifica a primeira chamada C após o restabelecimento.


## Gerar as tabelas a partir da campanha completa

Depois de concluir todas as fases, execute o pós-processamento em um diretório novo:

```sh
python3 -B -m validation.summarize \
  --campaign /tmp/flight-evaluation-final \
  --output /tmp/flight-evaluation-tables
```

O comando verifica a quantidade de casos, a sequência dos comandos, eventos e contadores posteriores a cada envio, as tolerâncias dos sensores, as interrupções e os hashes dos artefatos ARM. Uma campanha incompleta ou inconsistente não gera uma saída final. Os 11 CSVs, `summary.json` e `examples.json` preservam a ligação com os arquivos de entrada por SHA-256. O resumo não altera pacotes, tempos ou valores originais.

| Questão | Registros brutos | Tabelas geradas |
| --- | --- | --- |
| Q1 | `<alvo>/commands.json`, `<alvo>/downlink.jsonl` e catálogo | `q1_commands.csv`, `q1_attempts.csv` |
| Q2 | `registers/registers.json`, `<alvo>/sensors.json`, dumps de registradores | `q2_samples.csv`, `q2_errors.csv`, `physical_readings.csv` |
| Q3 | `registers/registers.json`, `native/dropout.json`, `physical/sensors.json` | `q3_interruptions.csv`, `q3_hal_samples.csv`, `q3_recovery.csv` |
| Q4 | `qemu/artifacts.json`, `physical/artifacts.json` | `q4_artifacts.csv` |
| Q5 | `build-*/metrics.json`, `cycles-native/metrics.json`, `starts-*/metrics.json`, `boots-qemu/metrics.json` e logs | `q5_timings.csv`, `q5_statistics.csv` |

Na publicação, mantenha os dados brutos em `validation/results/final/raw/` e as tabelas em `validation/results/final/tables/`, com um índice e manifesto SHA-256. O pós-processamento pode ser repetido usando `raw/` como `--campaign`. A revisão do código executado fica em `raw/prepare.json`; a revisão que publica os resultados é posterior e deve ser identificada separadamente. Não inclua o workspace `flight/`, imagens/discos, chaves SSH ou banco de runtime.
