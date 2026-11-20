# README specification

Rewrite `README.md` in Portuguese (the current language of the repository), simple and didactic, for someone who has never used cFS, Docker or QEMU. Every command must be copy-paste ready and verified on a clean checkout before you finish (record the verification in `RESULTS.md`). Use GitHub-rendered Mermaid diagrams. Put screenshots in `docs/images/` and keep them current (1440×900, dark).

Keep it scannable: short sections, tables for choices, one diagram per idea. No marketing language. State clearly at the top that Flight Studio is for learning and development and is never for flight.

## Required sections, in this order

1. **O que é** (2 to 3 lines and one screenshot of the Welcome or Target screen). What you will be able to do after the first run.
2. **Começar em 5 minutos (Native)**. Prerequisites per distribution in a table (Debian/Ubuntu, Fedora, Arch, openSUSE) with the exact install command; then:
   ```sh
   git clone -b first-flight-flow https://github.com/Raiagues/cfs_emulator.git
   cd cfs_emulator
   ./start
   ```
   Then "abra http://127.0.0.1:8765" and what the first screen shows. If the port is busy: `./start --ui --port 8766`.
3. **O primeiro voo** — the nine steps as a table (Passo · O que você faz · O que você vê · Onde isso existe no cFS real), plus the journey diagram from `03_FIRST_RUN_FLOW.md`.
4. **Três alvos** — a diagram and a table:
   ```mermaid
   flowchart LR
     subgraph PC[Seu computador]
       UI[Flight Studio\nnavegador] --> SRV[./start]
       SRV --> N[cFS nativo\nprocesso Linux]
       SRV --> D[Docker]
       D --> Q[QEMU raspi4b\nRaspberry Pi OS] --> CQ[cFS ARM64]
       GS[Ground station\nUDP] <--> N
       GS <--> CQ
     end
     SRV -- SSH --> PI[Raspberry Pi 4B real] --> CP[cFS ARM64]
     GS <--> CP
   ```
   Table: target · what you need · how to prepare · how to run · limits (Native: no real pins; Emulator: slow without KVM, virtual devices only; Board: needs a Pi 4B with 64-bit Raspberry Pi OS and SSH).
5. **Como os dados circulam** — one diagram: Ground station → UDP → ci_lab → Software Bus → apps → to_lab → UDP → Ground station; sensors → QMP (emulator) or file transport (native) → device → driver → app.
6. **Usar só pelo terminal** — every UI action with its CLI twin, grouped: preparar, compilar, executar, parar, emulador, apps e bibliotecas, sensores e cenários, ground station. Each with one example and its expected last line of output.
7. **Fazer o mesmo sem o Flight Studio** — the official cFS route, so the person can work on their own:
   ```sh
   git clone https://github.com/nasa/cFS.git
   cd cFS
   git submodule init
   git submodule update
   cp cfe/cmake/Makefile.sample Makefile
   cp -r cfe/cmake/sample_defs sample_defs
   make SIMULATION=native prep
   make
   make install
   cd build/exe/cpu1/
   ./core-cpu1
   ```
   Then how to send commands with the official ground tools (cFS-GroundSystem), and how to boot Raspberry Pi OS in QEMU `-M raspi4b` yourself (kernel, device tree, disk, usb-net, SSH port forward), referencing what `scripts/emulator.sh` does line by line.
8. **Estrutura do repositório** — table of folders and what each owns (from `02_ARCHITECTURE.md`), and which parts are graphical vs infrastructure.
9. **Testes** — how to run the unit tests, the browser tests and the follow-the-highlight tests; how to run the design previews in `docs/design-pack/design/preview/`.
10. **Problemas comuns** — table: symptom · cause · fix. At least: port in use; missing PyQt5/pyzmq; Docker group not active after install (log out and in); QEMU very slow without KVM (expected, times); SSH host key changed after recreating the emulator disk; telemetry not arriving (dest_IP, firewall); cFS already running (Stop cFS); not enough disk for the image.
11. **Licença e créditos** — Apache 2.0 for cFS components, credit to NASA cFS, QEMU, Raspberry Pi OS.

## Style rules

- Sentences short; one idea per sentence; no jargon without a one-line explanation the first time.
- Every diagram has a one-sentence caption under it.
- Every command block says where to run it (repo root, inside `cFS/`, inside the guest).
- No screenshot older than the code it shows.
