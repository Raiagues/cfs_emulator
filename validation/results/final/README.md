# Avaliação técnica — 23 de novembro de 2026

Campanha final executada pelo backend, sem navegador durante as medições. As capturas em `illustrations/` foram feitas posteriormente com a missão QEMU real e não integram as contagens quantitativas.

- Código e protocolo executados: [`64add2472dbf6869563612cf6b2c427b181dba5d`](https://github.com/Raiagues/cfs_emulator/tree/64add2472dbf6869563612cf6b2c427b181dba5d).
- Fonte oficial NASA: [`a4d305dc06fb7d468f5b45214d9f730b97d4bd77`](https://github.com/nasa/cFS/tree/a4d305dc06fb7d468f5b45214d9f730b97d4bd77), obtida pelo instalador público via rede. Os 4.458 arquivos originais rastreados permaneceram inalterados até o fim da campanha.
- A revisão de publicação dos dados é o commit que contém este diretório. Ela é posterior à revisão executada: inclui o pós-processamento e os dados, sem alterar o código de voo medido.
- [Protocolo e comandos de reprodução](../../README.md), [templates e scripts](../../../docs/templates-e-testes.md), [resumo verificável](tables/summary.json), [manifesto da cópia](procedure/package-manifest.json) e [SHA-256 dos arquivos](SHA256SUMS).

## Resultados e localização da evidência

| Questão | Resultado observado | Evidência |
| --- | --- | --- |
| Q1 — resposta a comandos | 36/36 envios confirmados em cada alvo; 108/108 no total. Quatro aplicações, três repetições de NOOP → RESET_COUNTERS → NOOP. | [Cada tentativa e seus contadores](tables/q1_attempts.csv), [contagem por aplicação/comando](tables/q1_commands.csv); `raw/{native,qemu,physical}/commands.json`, catálogo e `downlink.jsonl`. |
| Q2 — entrada conhecida | HAL C: 27 execuções e 405 aquisições, incluindo os intervalos de ausência de Q3. Native e QEMU: nove casos e 45 pacotes de sensores por alvo; valores válidos dentro dos limites por canal. | [Entradas e saídas](tables/q2_samples.csv), [erros e limites](tables/q2_errors.csv), `raw/registers/registers.json`, `raw/{native,qemu}/sensors.json`. |
| Q3 — ausência reportada como leitura inválida | Nove interrupções HAL: 45 leituras inválidas e recuperação na primeira aquisição C. Três interrupções Native: 15 pacotes inválidos; retorno válido observado entre 1,879 e 1,895 s, dentro do limite de 8 s. Placa: cinco pacotes inválidos de cada um dos dois sensores ausentes. | [Interrupções](tables/q3_interruptions.csv), [HAL por aquisição](tables/q3_hal_samples.csv), [recuperação UDP](tables/q3_recovery.csv), `raw/native/dropout.json`, `raw/physical/sensors.json`. |
| Q4 — mesmos artefatos ARM | 63 arquivos idênticos nos dois alvos: executável, 24 módulos, 37 tabelas e arquivo de inicialização. Mesmo fingerprint de build. | [Hashes por arquivo](tables/q4_artifacts.csv), `raw/{qemu,physical}/artifacts.json`. |
| Q5 — tempos descritivos | Dez ciclos de desenvolvimento Native, dez inícios cFS por alvo, cinco boots do guest QEMU e um build completo por arquitetura. | [Tempos individuais](tables/q5_timings.csv), [N, mínimo, mediana, IQR e máximo](tables/q5_statistics.csv), `raw/*/metrics.json` e logs correspondentes. |

As 1.650 linhas de `q2_samples.csv` são observações **por canal**, não 1.650 pacotes. Na placa, somente o MPU6050 está conectado: cinco pacotes válidos, com sete canais descritos em [physical_readings.csv](tables/physical_readings.csv). A operadora informou que ele estava parado no chão; a orientação não foi controlada. Não há referência metrológica nem comparação de exatidão com o emulador.

O TMP105 em memória usa 12 bits e passo de 0,0625 °C, com arredondamento. O modelo QEMU manteve configuração `0x00`, 9 bits e passo de 0,5 °C, com truncamento; o limite do protocolo é 0,501 °C. A [leitura do registrador de configuração](raw/qemu/tmp105-configuration.json) registra essa condição. Cada erro é avaliado contra o limite do respectivo ambiente, sem pressupor quantização equivalente.

## Fronteiras dos tempos

| Operação | N | Mediana (s) | Mínimo–máximo (s) |
| --- | ---: | ---: | ---: |
| Criar app no Native | 10 | 1,568 | 1,268–1,720 |
| Compilar incrementalmente no Native | 10 | 32,164 | 31,691–76,395 |
| Excluir app no Native | 10 | 2,622 | 2,620–2,673 |
| Iniciar cFS Native até primeiro HK | 10 | 8,610 | 8,445–8,867 |
| Iniciar cFS QEMU até primeiro HK | 10 | 29,806 | 29,297–30,346 |
| Iniciar cFS físico até primeiro HK | 10 | 14,923 | 14,837–15,365 |
| Boot QEMU preparado, implantação e primeiro HK | 5 | 101,900 | 101,203–114,895 |

O `run` nos alvos ARM inclui transferência/implantação. O CSV separa `payload_transfer`, `operational_observed_s`, `run_total_s`, `ground_to_first_hk_s` e `total_to_first_hk_s`. OPERATIONAL e SSH são instantes observados no host. Nos cinco boots, a mediana do trabalho de boot foi 73,096 s; SSH foi observado em 69,267 s. Essas etapas não são tempos internos instrumentados do guest.

Os builds completos levaram 82,974 s (Native) e 122,082 s (ARM), N=1 cada. A restauração da missão após os dez ciclos não integra suas estatísticas. Preparação do compilador ARM, imagem QEMU e primeiro provisionamento do disco constam separadamente de `raw/setup-builder/`, `raw/setup-qemu-image-final/` e `raw/first-boot-qemu/`; não integram as cinco repetições de boot. A preparação do compilador utilizou camadas Docker em cache.

As operações medidas ocorreram sequencialmente, com um worker de compilação. O desktop e o serviço local da plataforma permaneceram disponíveis; a carga de fundo não foi rigidamente controlada. Repetições compartilham arquivos e caches. As medidas são descritivas, sem inferência de ganho estatístico ou generalização. Não há ensaio orbital ou de eclipse nesta campanha.

## Reproduzir as tabelas e conferir a integridade

No checkout que contém esta publicação:

```sh
python3 -B -m validation.summarize \
  --campaign validation/results/final/raw \
  --output /tmp/flight-tables-reproduced
cd validation/results/final
sha256sum -c SHA256SUMS
```

O diretório de saída deve ser novo. `summary.json` identifica cada entrada por SHA-256, a revisão executada e o hash do analisador. Datas de geração dos resumos podem mudar; os 11 CSVs devem ter conteúdo idêntico. Para executar novamente os ensaios, siga o [protocolo](../../README.md) em uma missão isolada. Os coordenadores de `procedure/` preservam o procedimento desta coleta, com caminhos locais explícitos que devem ser adaptados ao novo diretório; acesso SSH deve ser configurado privadamente.

Os registros brutos preservam seus bytes, valores, tempos, sequências e mensagens. O manifesto registra a seleção publicada e as verificações de cópia. O checkout NASA, builds, imagens Docker, discos e banco de runtime ficam fora do Git. A biblioteca de pós-processamento é `validation/summarize.py`; seus testes em `interface/tests/test_evaluation_summary.py` usam dados sintéticos apenas para verificar o analisador.

A figura [telemetria TMP105](illustrations/ground-qemu/ground-qemu-eval_temp-telemetry.png) mostra campos reais recebidos após a coleta. `Value=31500` é o inteiro da telemetria em milésimos de grau Celsius, equivalente a 31,5 °C. As contagens dessa sessão de ilustração não substituem os 108 comandos medidos. O [registro da captura](illustrations/ground-qemu/capture.json) contém pacotes, MIDs, hashes e a origem das rotas no código; o tutorial mostrado é intermediário e a interface permanece em desenvolvimento.
