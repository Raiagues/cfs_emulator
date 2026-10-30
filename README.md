# Raspberry Pi 4 cFS emulator

Run all commands on your **Linux PC**, from the repository directory.
The setup supports Ubuntu 24.04+ and Debian 13 on AMD64.

## Set up once

```bash
git clone https://github.com/Raiagues/cfs_emulator.git
cd cfs_emulator
./scripts/setup.sh
```

Run setup as your normal user. It uses `sudo` when needed to install missing
Docker, OpenSSH, and Buildx packages from the distribution's APT repositories.
It configures SSH automatically in `~/.ssh/cfs-emulator/`, outside the checkout,
and downloads the emulator image or builds it locally if unavailable.

If setup adds you to the Docker group, **sign out and sign back in** before
continuing.

## Boot Linux

```bash
./boot.sh
```

The emulator runs in the background. This command waits until SSH login works
and prints `Raspberry Pi ready...` before returning. The first boot can take
several minutes.

## Upload and run cFS

Provide a precompiled **ARM64** directory containing `core-cpu1` and `cf/`.
Setup does not build or provide this cFS payload. The default directory is
`cFS/build-rpi_linux/exe/cpu1`:

```bash
./run.sh
```

To use a build elsewhere, run `./run.sh /path/to/cpu1` instead, replacing the
path with the absolute path to your build directory on the PC.

The command shows SCP upload progress, starts cFS, and follows its logs. Look
for `CFE_ES_Main entering OPERATIONAL state`. Press Ctrl+C to stop following
logs; cFS keeps running. Run `./run.sh` again to upload an updated build while
Linux stays running.

## Control

| Command | Action |
| --- | --- |
| `./logs.sh` | Follow the emulator's boot and serial logs. |
| `./stop.sh` | Shut down the emulator. |
| `./boot.sh --interactive` | Boot with the serial console attached. |
| `ssh -F ~/.ssh/cfs-emulator/config pi4-cfs` | Open a guest shell. |

Guest files in `board/` survive restarts. Keep the SSH identity in
`~/.ssh/cfs-emulator/` to retain access to the existing guest disk.
