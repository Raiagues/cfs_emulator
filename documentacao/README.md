# Raspberry Pi 4 cFS emulator

Run the PC commands below from the project directory on Linux. Docker and the
OpenSSH client must be available. If you do not have an SSH key yet, create one
with `ssh-keygen -t ed25519` before booting.

## Build and boot Linux

```bash
./build.sh                       # Build the configured base image once.
./boot.sh                        # Use ~/.ssh/id_ed25519.pub on the first boot.
# Or: ./boot.sh /path/to/key.pub
```

The first terminal becomes the guest serial console, with automatic login as
`root` for local development. The base image contains no cFS binaries, and the
installed `cfs.service` runs only on demand. Linux can boot without a compiled
cFS payload.

The first run creates the persistent disk `board/raspios.qcow2` and installs
the selected public key. Later runs reuse that disk without copying binaries
or changing its authorized keys. The private key stays on the PC.

Snapshots are disabled: Linux retains its first-boot setup, SSH identity, and
uploaded files. Subsequent boots skip the disk copy and guestfish preparation.
The Dockerfile configures networking and disables cloud-init and network
wait services that delayed this local emulator's startup.

Rebuilding Docker updates the base image, not an existing guest disk. When
migrating from the previous `start.sh` setup, shut down that emulator first,
then preserve its disk before booting this version:

```bash
mkdir -p board/before-interactive
mv -n board/raspios.qcow2 board/before-interactive/raspios.qcow2
./boot.sh
```

Skip the move if it has already been done. The new guest starts clean; files
from the old guest remain in the backup disk.

In a second PC terminal, connect over SSH:

```bash
ssh -p 2222 root@127.0.0.1
```

Use `exit` to return to the PC shell before running the upload commands below.

SSH is published only on the PC's localhost address and accepts public keys
only. The guest generates its SSH host keys on first boot; verify and accept
the host fingerprint when prompted. You can display it in the guest console
with `ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub`.

If you selected a nondefault key, add
`-i /path/to/private_key` to the PC's `ssh` and `scp` commands, and load that key
with `ssh-add /path/to/private_key` so `./stop.sh` can also use it.

## Upload and run cFS manually

Prepare the compiled ARM64 payload on the PC at
`cFS/build-rpi_linux/exe/cpu1`, including `core-cpu1` and `cf`. Then run these
commands from a PC terminal:

```bash
ssh -p 2222 root@127.0.0.1 systemctl stop cfs.service
ssh -p 2222 root@127.0.0.1 mkdir -p /opt/cFS/build-rpi_linux/exe
scp -P 2222 -r cFS/build-rpi_linux/exe/cpu1 \
    root@127.0.0.1:/opt/cFS/build-rpi_linux/exe/
ssh -p 2222 root@127.0.0.1 systemctl start cfs.service
ssh -p 2222 root@127.0.0.1 journalctl -u cfs.service -f
```

Successful startup includes `CFE_ES_Main entering OPERATIONAL state`. Press
Ctrl+C to stop following the journal; cFS keeps running.

Repeat the stop, upload, and start commands after compiling changes. Stop cFS
before replacing its files. No Docker rebuild or Linux restart is needed.
The recursive upload overwrites matching files and retains other files already
in the guest's `cpu1` directory.

To stop only cFS while leaving Linux running:

```bash
ssh -p 2222 root@127.0.0.1 systemctl stop cfs.service
```

Start cFS manually after each Linux boot. The service does not start
automatically.

## Logs and shutdown

```bash
./logs.sh   # Follow the latest serial-console log; Ctrl+C stops following.
./stop.sh   # Request a graceful Linux shutdown over SSH.
```

Serial logs are saved in `logs/`, with `logs/latest.log` pointing to the latest
run. Use `journalctl -u cfs.service -f` inside the guest for cFS service output.

Wait for the original console terminal to return to the PC shell before
running `./boot.sh` again. Files uploaded or changed in Linux remain on
`board/raspios.qcow2` across shutdowns. Shut Linux down cleanly to preserve
those writes.

If you intentionally replace the disk with a clean image, its SSH host key
will change. Verify that the replacement was intentional before removing the
old entry:

```bash
ssh-keygen -R '[127.0.0.1]:2222'
```

Reconnect and verify the new fingerprint. Do not bypass host-key checking.
