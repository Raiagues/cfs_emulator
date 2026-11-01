#!/usr/bin/env bash
set -euo pipefail

# Validate devices before opening the guest disk.
mkdir -p board
python3 sensors/runtime.py args > board/qemu-devices.args
mapfile -d '' -t SENSOR_ARGS < board/qemu-devices.args

# Initialize a persistent disk and its SSH key only on the first run.
if [[ ! -e board/raspios.qcow2 ]]; then
    echo "Preparing the guest disk for its first boot..."
    cp /opt/raspi-os/raspios.qcow2 board/raspios.qcow2.new
    # Provision without a command history in the host user's home directory.
    env -u HOME guestfish --rw -a board/raspios.qcow2.new \
        run : mount /dev/sda2 / : \
        mkdir-p /root/.ssh : chmod 0700 /root/.ssh : \
        upload /ssh.pub /root/.ssh/authorized_keys : \
        chmod 0600 /root/.ssh/authorized_keys
    # Keep this disk's kernel and device tree together across image updates.
    cp /opt/raspi-os/kernel8.img /opt/raspi-os/bcm2711-rpi-4-b.dtb \
        /opt/raspi-os/initramfs8 board/
    mv board/raspios.qcow2.new board/raspios.qcow2
    sync -f board/raspios.qcow2
fi

# Retain guest changes. The inactive watchdog driver provides clean power-off.
python3 sensors/runtime.py record
exec qemu-system-aarch64 -M raspi4b \
    -kernel board/kernel8.img \
    -dtb board/bcm2711-rpi-4-b.dtb \
    -initrd board/initramfs8 \
    -drive file=board/raspios.qcow2,if=sd,format=qcow2 \
    -append "console=ttyAMA1 root=/dev/mmcblk1p2 rw rootwait watchdog_disarm=0" \
    -display none \
    -chardev stdio,id=console,signal=off,logfile="$1" \
    -serial chardev:console -monitor none \
    -qmp unix:/work/board/qmp.sock,server=on,wait=off \
    -netdev user,id=net0,hostfwd=tcp:0.0.0.0:2222-:22 \
    -device usb-net,netdev=net0 "${SENSOR_ARGS[@]}"
