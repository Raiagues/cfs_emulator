#!/usr/bin/env bash
set -euo pipefail

mkdir -p board

# Initialize a persistent disk and its SSH key only on the first run.
if [[ ! -e board/raspios.qcow2 ]]; then
    echo "Preparing the guest disk for its first boot..."
    cp --sparse=always /opt/raspi-os/raspios.qcow2 board/raspios.qcow2.new
    # Provision without a command history in the host user's home directory.
    echo "[emulator] Disk copied. Provisioning the guest SSH key."
    env -u HOME guestfish --rw -a board/raspios.qcow2.new \
        run : mount /dev/sda2 / : \
        mkdir-p /root/.ssh : chmod 0700 /root/.ssh : \
        upload /ssh.pub /root/.ssh/authorized_keys : \
        chmod 0600 /root/.ssh/authorized_keys : \
        mkdir-p /etc/systemd/system/ssh.service.d : \
        write /etc/systemd/system/ssh.service.d/flight-studio-console.conf \
        $'[Service]\nExecStartPost=/bin/sh -c "echo FLIGHT_STUDIO_SSH_READY >/dev/ttyAMA1"\n'
    # Keep this disk's kernel and device tree together across image updates.
    cp /opt/raspi-os/kernel8.img /opt/raspi-os/bcm2711-rpi-4-b.dtb \
        /opt/raspi-os/initramfs8 board/
    mv board/raspios.qcow2.new board/raspios.qcow2
    sync -f board/raspios.qcow2
fi

# Retain guest changes. The inactive watchdog driver provides clean power-off.
python3 sensors/runtime.py boot > board/qemu-devices.args
mapfile -d '' -t SENSOR_ARGS < board/qemu-devices.args
echo "[emulator] Disk ready. Starting the guest kernel."
exec qemu-system-aarch64 -M raspi4b \
    -kernel board/kernel8.img \
    -dtb board/mission.dtb \
    -initrd board/initramfs8 \
    -drive file=board/raspios.qcow2,if=sd,format=qcow2 \
    -append "console=ttyAMA1 root=/dev/mmcblk1p2 rw rootwait watchdog_disarm=0" \
    -display none \
    -chardev stdio,id=console,signal=off,logfile="$1" \
    -serial chardev:console -monitor none \
    -qmp "tcp:0.0.0.0:$STUDIO_QMP_INTERNAL,server=on,wait=off" \
    -netdev "user,id=net0,hostfwd=tcp:0.0.0.0:$STUDIO_SSH_INTERNAL-:22,hostfwd=udp:0.0.0.0:$STUDIO_CI_GUEST-:$STUDIO_CI_GUEST" \
    -device usb-net,netdev=net0 "${SENSOR_ARGS[@]}"
