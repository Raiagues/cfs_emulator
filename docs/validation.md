# Validação do Flight Studio

## Suítes automatizadas

| Ambiente | Python | JavaScript |
| --- | --- | --- |
| Checkout com o cFS oficial instalado, após a revisão de navegação | 79 de 79 passaram, incluindo os ciclos HTTP de missão e hardware e o redirecionamento para o setup antes do clone. | 33 de 33 passaram. |
| Projeto antes do clone, ensaio anterior | 61 passaram. Os dois ciclos HTTP que dependem dos fontes oficiais foram pulados. | 20 de 20 passaram. |

## Primeiro voo nativo

Em 19 de novembro de 2026, o primeiro voo foi executado em cópias isoladas do projeto em Linux x86-64. A missão inicial continha as apps da NASA e nenhum barramento ou sensor cadastrado. Uma segunda cópia começou inclusive sem o diretório `cFS/` para verificar o reparo pelo navegador. O projeto de trabalho ficou disponível para repetir a instalação desde o início.

| Ensaio | Observação |
| --- | --- |
| Setup e instalação | Com **Source** pendente, **Continue** ficou indisponível. Clicar em **+** executou o clone oficial com submódulos, exibiu a transferência no terminal e repetiu a verificação. O checkout usado no voo foi `a4d305dc06fb`. |
| Boot | O build produziu `core-cpu1`. O processo imprimiu `CFE_ES_Main entering OPERATIONAL state`. As marcas das apps vieram das respectivas mensagens de inicialização. |
| Reprodução do boot | O registro nativo continha 30 transições até OPERATIONAL e 13 apps de startup. No Chromium, foi possível pausar e reproduzir o registro, abrir as seis camadas e inspecionar o console. |
| Primeiro contato | A conexão iniciou com **zero** comandos. **TO_LAB_OUTPUT_ENABLE_CC** transmitiu 24 bytes. O **NOOP** de **sample_app** devolveu o evento de informação nº 3, na nave 66, processador 1. O housekeeping registrou o aumento de `CommandCounter`. |
| Assistente e editor | Em Chromium, **orbit_reader** gerou um plano com 78 arquivos. O salvamento apresentou os quatro MIDs do plano. A atividade **capture** começou em **0/7**. Os sete passos abriram, e retornar ao editor pela barra lateral fechou a atividade. |
| Comando da missão | Em **orbit_demo**, foi criado o handler de **stamp** e gravado o C com a revisão esperada. Após recompilar, o catálogo dava MID **0x1A00**, FC **4**. O envio com `Value=17` transmitiu `1a00c0000005043511000000`. |
| Do editor ao alvo | No Chromium, o assistente criou `orbit_demo` em uma missão nativa vazia. A etapa **Handler** abriu o trecho a implementar. Salvamos o C, seguimos **Test → Open Ground Station**, paramos o binário anterior e iniciamos o novo build pelo mesmo fluxo. A estação abriu `ORBIT_DEMO_STAMP_CC`. |
| Ida e volta confirmada | No editor de testes da estação, configuramos o evento da app e o incremento de `CommandCounter`. O pacote com `Value=17` voltou como **Stamp 17 received**, evento **3** de **ORBIT_DEMO**, sequência CCSDS **42**. O housekeeping separado registrou **0 → 1**, sequência **29**. A estação confirmou as duas observações. |
| Reinício do guia | Com uma alteração C em memória, **Start over** voltou a **0/9** no mesmo editor. O texto permaneceu no buffer. O documento coube em 1440 × 900, 1366 × 768 e 390 × 844. |
| Progresso entre sessões | Esse voo concluiu **Target, Boot, Event, App, Command e Send**. Uma nova conexão voltou a aguardar o evento da sessão. Reabrir o backend preservou o resultado comprovado de **Send**. |
| Temperatura | Na órbita de teste, com 1U, 1,3 kg, α = ε = 0,7 e 1 W, a temperatura variou de **−9,27 a 8,58 °C**. Os equilíbrios sob iluminação e em sombra foram **33,49 °C** e **−82,81 °C**. |
| Testes de sinais | Os três cenários foram executados pelo botão **Run**. A curva enviada foi comparada com a leitura do HAL C em um barramento de teste local. O cenário de desconexão verificou o erro e a recuperação do dispositivo. |

![Teste Stamp concluído com os dois recibos da app](images/first-flight/command-receipt.webp)

## Retomada no emulador

Em 19 de novembro de 2026, o Raspberry Pi OS emulado já havia chegado ao login, mas a tentativa de boot do Studio terminou em `Host key verification failed`. O disco recriado tinha outra chave. Conferimos a identidade ED25519 no contêiner que montava o disco do projeto, exigimos essa chave na porta 2222 e retomamos o primeiro voo no mesmo contêiner.

| Verificação | Resultado observado |
| --- | --- |
| Binário e destino | cFS oficial `a4d305dc06fb`, build ARM64, guest `aarch64`. |
| Processo e journal | `cfs.service` ativo, PID 1023. O journal dessa invocação registrou os cinco estados do ES, até `CFE_ES_Main entering OPERATIONAL state`. |
| Retomada do console | Ao reiniciar o servidor do Studio, o mesmo serviço continuou em OPERATIONAL. Um leitor identificado pela invocação systemd recuperou o evento de inicialização **MD/1** e seguiu recebendo novas linhas. |
| Apps | 13 entradas no startup. Doze apps emitiram seu evento EVS de inicialização. `sch_lab` confirmou a inicialização em texto no console. Seu chip aguarda um evento EVS identificado. |
| Navegador | A faixa exibiu o build, o emulador e os cinco marcos de início do cFS. Abrir o console preservou a posição da pilha. Na versão atual, o espaço entre o rodapé e o fim da janela ficou em 18 px a 1440 × 900 e 8 px a 1366 × 768. Em OPERATIONAL, **Next** abriu a etapa **Event** no mesmo documento. |

Com a placa física salva no setup e o voo ativo no QEMU, abrimos o Boot diretamente e acompanhamos os quadros renderizados no Chromium. O guia marcou **Boot**, com **Target** e **Boot** concluídos. Ao clicar em **Next**, apareceu **Event**. A estação leu o catálogo do emulador e selecionou `TO_LAB_OUTPUT_ENABLE_CC`. Voltar e avançar no navegador preservaram o alvo. A navegação enviou somente requisições de leitura.

Repetimos o percurso nos dois temas, em 1440 × 900 e 1366 × 768, com atraso adicional de 370 ms nas leituras do hardware, da missão e do catálogo. A tela identificou a área durante o carregamento e coube na janela. Em um ensaio separado, interrompemos uma leitura da missão e outra do catálogo. **Retry** recuperou a estação no mesmo alvo.

[![Voo QEMU em OPERATIONAL na janela do Studio](images/first-flight/boot-qemu-running.webp)](images/first-flight/boot-qemu-running.webp)

## Comparação das telas

Cada linha traz o export interativo fornecido e a tela correspondente servida pelo Studio. As imagens abrem no tamanho original. O estado da missão varia entre os exemplos. As capturas do protótipo usam dados ilustrativos, e as do Studio consultam as missões de validação.

<details>
<summary>Escolha do alvo</summary>

As capturas mostram o estado depois de verificar **Native** em uma cópia nova. **Compiler** e **Python** passaram. **Source** aguarda a instalação. Na placa, confirmamos que **Save settings** persistiu o endereço pela API e que **Cancel** e Escape preservaram o valor anterior. Abrir os detalhes e o terminal manteve os cartões nas mesmas coordenadas em 1440 × 900, 1366 × 768 e 390 × 844. Em uma instalação de teste com PTY, **Input required** permitiu responder a uma solicitação de senha e acompanhar a verificação posterior. O tema claro da aplicação usa bege.

| Janela e tema | Referência | Flight Studio |
| --- | --- | --- |
| 1440 × 900, escuro | [![Referência, Escolha do alvo, escuro, 1440](images/first-flight/setup-1440-dark-design.webp)](images/first-flight/setup-1440-dark-design.webp) | [![Studio, Escolha do alvo, escuro, 1440](images/first-flight/setup-1440-dark-studio.webp)](images/first-flight/setup-1440-dark-studio.webp) |
| 1440 × 900, claro | [![Referência, Escolha do alvo, claro, 1440](images/first-flight/setup-1440-light-design.webp)](images/first-flight/setup-1440-light-design.webp) | [![Studio, Escolha do alvo, claro, 1440](images/first-flight/setup-1440-light-studio.webp)](images/first-flight/setup-1440-light-studio.webp) |
| 1366 × 768, escuro | [![Referência, Escolha do alvo, escuro, 1366](images/first-flight/setup-1366-dark-design.webp)](images/first-flight/setup-1366-dark-design.webp) | [![Studio, Escolha do alvo, escuro, 1366](images/first-flight/setup-1366-dark-studio.webp)](images/first-flight/setup-1366-dark-studio.webp) |
| 1366 × 768, claro | [![Referência, Escolha do alvo, claro, 1366](images/first-flight/setup-1366-light-design.webp)](images/first-flight/setup-1366-light-design.webp) | [![Studio, Escolha do alvo, claro, 1366](images/first-flight/setup-1366-light-studio.webp)](images/first-flight/setup-1366-light-studio.webp) |

</details>

<details>
<summary>Primeiro boot</summary>

As capturas mostram o voo QEMU no registro **Starting core**. A faixa superior exibe cada um dos cinco estados do núcleo. No Chromium, selecionar **Loading apps** mostrou as apps confirmadas até aquele registro e manteve **Operational** pendente. **Resume** voltou ao voo em execução. **Open console**, **Close console** e Escape mantiveram a posição da pilha. A página coube em 1440 × 900, 1366 × 768 e 390 × 844 nos dois temas.

| Janela e tema | Referência | Flight Studio |
| --- | --- | --- |
| 1440 × 900, escuro | [![Referência, Primeiro boot, escuro, 1440](images/first-flight/boot-1440-dark-design.webp)](images/first-flight/boot-1440-dark-design.webp) | [![Studio, Primeiro boot, escuro, 1440](images/first-flight/boot-1440-dark-studio.webp)](images/first-flight/boot-1440-dark-studio.webp) |
| 1440 × 900, claro | [![Referência, Primeiro boot, claro, 1440](images/first-flight/boot-1440-light-design.webp)](images/first-flight/boot-1440-light-design.webp) | [![Studio, Primeiro boot, claro, 1440](images/first-flight/boot-1440-light-studio.webp)](images/first-flight/boot-1440-light-studio.webp) |
| 1366 × 768, escuro | [![Referência, Primeiro boot, escuro, 1366](images/first-flight/boot-1366-dark-design.webp)](images/first-flight/boot-1366-dark-design.webp) | [![Studio, Primeiro boot, escuro, 1366](images/first-flight/boot-1366-dark-studio.webp)](images/first-flight/boot-1366-dark-studio.webp) |
| 1366 × 768, claro | [![Referência, Primeiro boot, claro, 1366](images/first-flight/boot-1366-light-design.webp)](images/first-flight/boot-1366-light-design.webp) | [![Studio, Primeiro boot, claro, 1366](images/first-flight/boot-1366-light-studio.webp)](images/first-flight/boot-1366-light-studio.webp) |

</details>

<details>
<summary>Arquitetura e criação</summary>

A missão da captura começou vazia na seção Your apps. Os nomes do restante da arquitetura vêm dos módulos incluídos no checkout.

| Janela e tema | Referência | Flight Studio |
| --- | --- | --- |
| 1440 × 900, escuro | [![Referência, Arquitetura e criação, escuro, 1440](images/first-flight/home-1440-dark-design.webp)](images/first-flight/home-1440-dark-design.webp) | [![Studio, Arquitetura e criação, escuro, 1440](images/first-flight/home-1440-dark-studio.webp)](images/first-flight/home-1440-dark-studio.webp) |
| 1440 × 900, claro | [![Referência, Arquitetura e criação, claro, 1440](images/first-flight/home-1440-light-design.webp)](images/first-flight/home-1440-light-design.webp) | [![Studio, Arquitetura e criação, claro, 1440](images/first-flight/home-1440-light-studio.webp)](images/first-flight/home-1440-light-studio.webp) |
| 1366 × 768, escuro | [![Referência, Arquitetura e criação, escuro, 1366](images/first-flight/home-1366-dark-design.webp)](images/first-flight/home-1366-dark-design.webp) | [![Studio, Arquitetura e criação, escuro, 1366](images/first-flight/home-1366-dark-studio.webp)](images/first-flight/home-1366-dark-studio.webp) |
| 1366 × 768, claro | [![Referência, Arquitetura e criação, claro, 1366](images/first-flight/home-1366-light-design.webp)](images/first-flight/home-1366-light-design.webp) | [![Studio, Arquitetura e criação, claro, 1366](images/first-flight/home-1366-light-studio.webp)](images/first-flight/home-1366-light-studio.webp) |

No Chromium, a partir dessa missão, foi possível criar a app `orbit_reader`, adicionar o barramento `i2c-bus.1`, conectar um TMP105 em `0x48` e vincular seu leitor HAL. Selecionar a app em 3D destacou as dependências até o barramento e os quatro fios do sensor. Também foi possível alterar o zoom, girar o desenho e selecionar o sensor pelo teclado para consultar a pinagem. A indicação de seleção e os controles ficaram dentro da janela nos dois tamanhos e temas.

[![Seleção da app orbit_reader com a conexão ao sensor em 3D](images/first-flight/home-linked-sensor.webp)](images/first-flight/home-linked-sensor.webp)

</details>

<details>
<summary>Ground Station</summary>

A captura foi feita no primeiro contato, antes da telemetria. O formulário mostra o destino IPv4 da conexão e o tamanho do pacote de habilitação do catálogo. O seletor **Round trip / System overview** também abre a visão geral. As setas internas indicam a arquitetura e só recebem confirmação quando existe uma observação correspondente.

| Janela e tema | Referência | Flight Studio |
| --- | --- | --- |
| 1440 × 900, escuro | [![Referência, Ground Station, escuro, 1440](images/first-flight/ground-1440-dark-design.webp)](images/first-flight/ground-1440-dark-design.webp) | [![Studio, Ground Station, escuro, 1440](images/first-flight/ground-1440-dark-studio.webp)](images/first-flight/ground-1440-dark-studio.webp) |
| 1440 × 900, claro | [![Referência, Ground Station, claro, 1440](images/first-flight/ground-1440-light-design.webp)](images/first-flight/ground-1440-light-design.webp) | [![Studio, Ground Station, claro, 1440](images/first-flight/ground-1440-light-studio.webp)](images/first-flight/ground-1440-light-studio.webp) |
| 1366 × 768, escuro | [![Referência, Ground Station, escuro, 1366](images/first-flight/ground-1366-dark-design.webp)](images/first-flight/ground-1366-dark-design.webp) | [![Studio, Ground Station, escuro, 1366](images/first-flight/ground-1366-dark-studio.webp)](images/first-flight/ground-1366-dark-studio.webp) |
| 1366 × 768, claro | [![Referência, Ground Station, claro, 1366](images/first-flight/ground-1366-light-design.webp)](images/first-flight/ground-1366-light-design.webp) | [![Studio, Ground Station, claro, 1366](images/first-flight/ground-1366-light-studio.webp)](images/first-flight/ground-1366-light-studio.webp) |

</details>

<details>
<summary>Atividade de código</summary>

O símbolo, o caminho no projeto e o número de linha pertencem à app criada no teste. A atividade começa com zero etapas percorridas.

| Janela e tema | Referência | Flight Studio |
| --- | --- | --- |
| 1440 × 900, escuro | [![Referência, Atividade de código, escuro, 1440](images/first-flight/code-1440-dark-design.webp)](images/first-flight/code-1440-dark-design.webp) | [![Studio, Atividade de código, escuro, 1440](images/first-flight/code-1440-dark-studio.webp)](images/first-flight/code-1440-dark-studio.webp) |
| 1440 × 900, claro | [![Referência, Atividade de código, claro, 1440](images/first-flight/code-1440-light-design.webp)](images/first-flight/code-1440-light-design.webp) | [![Studio, Atividade de código, claro, 1440](images/first-flight/code-1440-light-studio.webp)](images/first-flight/code-1440-light-studio.webp) |
| 1366 × 768, escuro | [![Referência, Atividade de código, escuro, 1366](images/first-flight/code-1366-dark-design.webp)](images/first-flight/code-1366-dark-design.webp) | [![Studio, Atividade de código, escuro, 1366](images/first-flight/code-1366-dark-studio.webp)](images/first-flight/code-1366-dark-studio.webp) |
| 1366 × 768, claro | [![Referência, Atividade de código, claro, 1366](images/first-flight/code-1366-light-design.webp)](images/first-flight/code-1366-light-design.webp) | [![Studio, Atividade de código, claro, 1366](images/first-flight/code-1366-light-studio.webp)](images/first-flight/code-1366-light-studio.webp) |

</details>

<details>
<summary>Sensores e órbita</summary>

Os números e curvas vêm dos dispositivos configurados e do modelo de sinal. O emulador estava desligado nas capturas e o controle de envio exibe esse estado. Os cenários locais identificam a leitura como **Local HAL read**. A telemetria de voo tem origem no downlink.

| Janela e tema | Referência | Flight Studio |
| --- | --- | --- |
| 1440 × 900, escuro | [![Referência, Sensores e órbita, escuro, 1440](images/first-flight/sensors-1440-dark-design.webp)](images/first-flight/sensors-1440-dark-design.webp) | [![Studio, Sensores e órbita, escuro, 1440](images/first-flight/sensors-1440-dark-studio.webp)](images/first-flight/sensors-1440-dark-studio.webp) |
| 1440 × 900, claro | [![Referência, Sensores e órbita, claro, 1440](images/first-flight/sensors-1440-light-design.webp)](images/first-flight/sensors-1440-light-design.webp) | [![Studio, Sensores e órbita, claro, 1440](images/first-flight/sensors-1440-light-studio.webp)](images/first-flight/sensors-1440-light-studio.webp) |
| 1366 × 768, escuro | [![Referência, Sensores e órbita, escuro, 1366](images/first-flight/sensors-1366-dark-design.webp)](images/first-flight/sensors-1366-dark-design.webp) | [![Studio, Sensores e órbita, escuro, 1366](images/first-flight/sensors-1366-dark-studio.webp)](images/first-flight/sensors-1366-dark-studio.webp) |
| 1366 × 768, claro | [![Referência, Sensores e órbita, claro, 1366](images/first-flight/sensors-1366-light-design.webp)](images/first-flight/sensors-1366-light-design.webp) | [![Studio, Sensores e órbita, claro, 1366](images/first-flight/sensors-1366-light-studio.webp)](images/first-flight/sensors-1366-light-studio.webp) |

</details>

### Assistente de app

| O que é | Arquivos da proposta | Gravação confirmada |
| --- | --- | --- |
| ![Nome](images/first-flight/wizard-name.webp) | ![Arquivos](images/first-flight/wizard-files.webp) | ![MIDs da app criada](images/first-flight/wizard-created.webp) |

## Ensaios anteriores em bancada

Registros da versão anterior cobrem o Raspberry Pi OS no emulador e uma Raspberry Pi 4 Model B Rev 1.5. Na placa física, a missão foi ensaiada com as apps padrão. A aquisição dos três sensores foi medida no QEMU.

| Cenário | Resultado observado |
| --- | --- |
| Configuração da bancada | No Chromium, uma missão vazia passou por **Add bus → Connect sensor → Link HAL → Open reader**. O editor abriu o leitor C gerado para o TMP105. A mesma ação contextual ficou visível nas projeções 2D e 3D. |
| Barramento no Linux emulado | Em dois boots isolados do Raspberry Pi OS com kernel aarch64 6.18.50, a missão vazia produziu um controlador desabilitado e nenhum `/dev/i2c-1`. Após selecionar o barramento e conectar um TMP105, o kernel criou o dispositivo. O registro I²C do chip em `0x48`, lido via SSH, retornou 24,5 °C após a escrita QMP de 24.500 m°C. |
| Órbita e sinal no guest | Em um terceiro boot, `orbit.sunlight` usou 15,5 °C de base e 4 °C de amplitude para o TMP105. Com o satélite iluminado, a prévia calculou 19,5 °C. A sessão escreveu 19.500 m°C pelo QMP e o registro de temperatura, lido dentro do guest em `/dev/i2c-1`, retornou 19,5 °C. |
| Instalação do zero | O instalador baixou o cFS e seus submódulos diretamente de `nasa/cFS`. Checkout independente `a4d305dc06fb`. Nenhum arquivo de `cFS/` é rastreado pelo Git da plataforma. |
| Missão nativa | Na revisão `93e589b86430`, adicionei `orbit_demo`, compilei e confirmei que a app inicializou. cFE entrou em `OPERATIONAL` como usuário normal. |
| Missão no checkout recém-baixado | Na revisão `a4d305dc06fb`, `thermal_demo` carregou junto com `hal_sensor`, `linux_i2c_lib` e `tmp105_lib`. O teste detectou um limite de nomes de pipes que impedia a app de iniciar. O overlay agora dimensiona o limite pelos nomes declarados. Após a correção, o log confirmou `THERMAL_DEMO Initialized` e o estado `OPERATIONAL`. A própria `THERMAL_DEMO` respondeu a `THERMAL_DEMO_NOOP_CC` por telemetria. |
| Ground Station nativa | Um `SAMPLE_APP_NOOP_CC` de 8 bytes recebeu o evento `SAMPLE: NOOP command v7.0.2-rc1-oss`. A sessão registrou 31 pacotes de telemetria. |
| Missão ARM64 | A app `science` foi compilada com leitores para TMP105, LSM303DLHC magnetômetro e MPU6050. A missão inicializou em Raspberry Pi OS no QEMU. |
| Aquisição real no modelo emulado | Três passos do gerador escreveram sinais por QMP. A leitura dos registradores pelo Linux do guest retornou os dados dos três chips. A app enviou os três pacotes à estação com `Valid = 1`, `Status = 0`, `ReadCounter = 176` e `ErrorCounter = 0`. O pacote do TMP105 continha `Value = 24000` na unidade do modelo, ou 24 °C. |
| Comando pelo navegador | O botão Send transmitiu `1882c000000100a4` ao QEMU. O evento NOOP da SAMPLE_APP voltou cerca de 432 ms depois nessa execução. O teste pela API também recebeu o evento, com 43 pacotes na sessão. |
| Placa física por SSH e UDP | Em uma Raspberry Pi 4 Model B Rev 1.5 com Linux aarch64, a missão padrão ARM64 compilada contra `a4d305dc06fb` chegou a `OPERATIONAL`. A Ground Station enviou `SAMPLE_APP_NOOP_CC`, recebeu 26 pacotes e o evento da SAMPLE_APP. O journal do serviço registrou o mesmo evento. |
| Edição e navegação | Criação, renomeação e remoção usando a API, ligação de leitores, edição C mantida após sincronização e rejeição de uma revisão antiga. No Chromium, o editor localizou o payload, o despacho, o handler e as anotações da app de teste. Para SAMPLE_APP_NOOP_CC, os seis saltos de código abriram as linhas do clone local, incluindo o protótipo e o evento EVS 3. As ferramentas Tags, Packet e Dispatch abriram no navegador e aceitaram fechamento com Escape. Em uma missão vazia, New mission app criou thermal_lab. Em seguida, com a fonte oficial de sample_app aberta, New command criou THERMAL_LAB_READ_PROBE_CC em thermal_lab. O editor coube em janelas de 1366 × 768, 390 × 844 e 844 × 390. |
| Round trip com cFS nativo | Em missão isolada, as 12 apps de distribuição com NOOP, a app de missão `thermal_demo` e os cinco serviços cFE com NOOP emitiram os eventos EVS esperados. O teste de `sample_app` também exigiu aumento do `CommandCounter` em um pacote de housekeeping distinto. O `sch_lab` estava carregado e seu catálogo não expôs um NOOP. |
| Instalação e terminal | Uma instalação temporária exercitou os estados pendente, em execução, sucesso e falha, os códigos de saída 7 e 0 e a retomada do mesmo terminal após recarregar a página. |

## Repetir

A suíte Python usa a biblioteca padrão e um compilador C no host. O teste HTTP utiliza o checkout instalado para montar uma missão em diretório temporário. Os testes de interface em JavaScript usam o executor de testes do Node. O Node só é necessário para essa suíte.

```sh
./scripts/install-cfs.sh
python3 -m unittest discover -s interface/tests -v
node --experimental-default-type=module --test interface/tests/*.mjs
```

Com a estação e o cFS em execução no alvo escolhido, use o teste de ponta a ponta para confirmar a resposta da app oficial pelo canal de telemetria.

```sh
python3 interface/tests/live_ground.py --target native
python3 interface/tests/live_ground.py --target qemu
```

Execute cada linha com o alvo correspondente ativo. O teste usa a sessão existente ou encerra apenas a conexão de Ground Station que ele próprio abriu. [Preparação e execução dos alvos](../README.md) · [Revisão do PR de rshz3028](pr-review.md).

Para repetir a verificação das apps em uma missão de teste, conecte a Ground Station, aguarde uma amostra de housekeeping e execute o comando abaixo. A saída contém o MID, a sequência CCSDS e os valores recebidos para cada NOOP. O script remove a definição de teste temporária após cada envio.

```sh
python3 interface/tests/live_round_trips.py --target native --port 8765
```
