FROM debian:trixie-slim AS cfs-builder

# Cross-compile cFS without installing a toolchain on the host PC.
RUN apt-get update && apt-get install -y --no-install-recommends build-essential cmake gcc-aarch64-linux-gnu g++-aarch64-linux-gnu git && rm -rf /var/lib/apt/lists/*
WORKDIR /cFS
CMD ["bash"]

FROM debian:trixie-slim AS base

# Install QEMU and required tools
RUN echo "deb http://deb.debian.org/debian trixie-backports main" > /etc/apt/sources.list.d/backports.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
    qemu-utils python3 curl ca-certificates xz-utils mtools \
    device-tree-compiler guestfish "linux-image-$(dpkg --print-architecture)" && \
    apt-get install -y --no-install-recommends -t trixie-backports qemu-system-arm && \
    rm -rf /var/lib/apt/lists/*

FROM base AS prepare

# Download Raspberry Pi OS
RUN mkdir -p /opt/raspi-os && \
    curl -fL https://downloads.raspberrypi.com/raspios_lite_arm64/images/raspios_lite_arm64-2026-10-06/2026-10-06-raspios-trixie-arm64-lite.img.xz | xz -dc > /opt/raspi-os/raspios.img

# Extract boot files and configure the emulated peripherals.
RUN BOOT_OFFSET=$(($(od -An -tu4 -j 454 -N 4 /opt/raspi-os/raspios.img) * 512)) && \
    mcopy -i "/opt/raspi-os/raspios.img@@$BOOT_OFFSET" ::kernel8.img /opt/raspi-os/kernel8.img && \
    mcopy -i "/opt/raspi-os/raspios.img@@$BOOT_OFFSET" ::bcm2711-rpi-4-b.dtb /opt/raspi-os/bcm2711-rpi-4-b.dtb && \
    mcopy -i "/opt/raspi-os/raspios.img@@$BOOT_OFFSET" ::initramfs8 /opt/raspi-os/initramfs8 && \
    fdtput -t s /opt/raspi-os/bcm2711-rpi-4-b.dtb /soc/i2c@7e804000 status okay && \
    fdtput -t s /opt/raspi-os/bcm2711-rpi-4-b.dtb /soc/serial@7e201000/bluetooth status disabled && \
    fdtput -t s /opt/raspi-os/bcm2711-rpi-4-b.dtb /soc/usb@7e980000 status okay && \
    fdtput -t s /opt/raspi-os/bcm2711-rpi-4-b.dtb /soc/usb@7e980000 compatible brcm,bcm2835-usb && \
    fdtput -t s /opt/raspi-os/bcm2711-rpi-4-b.dtb /soc/usb@7e980000 dr_mode host

# Configure Linux once. cFS is available as an optional, disabled service.
COPY cfs.service /tmp/cfs.service
COPY config/ /tmp/config/

RUN qemu-img convert -f raw -O qcow2 /opt/raspi-os/raspios.img /opt/raspi-os/raspios.qcow2 && \
    qemu-img resize /opt/raspi-os/raspios.qcow2 4G && \
    guestfish --rw -a /opt/raspi-os/raspios.qcow2 \
        run : mount /dev/sda2 / : \
        mkdir-p /opt/cFS/build-rpi_linux/exe/cpu1 : \
        upload /tmp/cfs.service /etc/systemd/system/cfs.service : \
        mkdir-p /etc/systemd/system/multi-user.target.wants : \
        ln-sf /dev/null /etc/systemd/system/userconfig.service : \
        touch /etc/cloud/cloud-init.disabled : \
        mkdir-p /etc/systemd/network : \
        upload /tmp/config/10-usb.network /etc/systemd/network/10-usb.network : \
        ln-sf /usr/lib/systemd/system/systemd-networkd.service /etc/systemd/system/multi-user.target.wants/systemd-networkd.service : \
        ln-sf /dev/null /etc/systemd/system/NetworkManager.service : \
        ln-sf /dev/null /etc/systemd/system/NetworkManager-wait-online.service : \
        ln-sf /dev/null /etc/systemd/system/systemd-networkd-wait-online.service : \
        ln-sf /dev/null /etc/systemd/system/rpi-eeprom-update.service : \
        mkdir-p /etc/systemd/system/serial-getty@ttyAMA1.service.d : \
        upload /tmp/config/serial-console.conf /etc/systemd/system/serial-getty@ttyAMA1.service.d/override.conf : \
        mkdir-p /etc/systemd/system.conf.d : \
        upload /tmp/config/watchdog.conf /etc/systemd/system.conf.d/90-qemu-watchdog.conf : \
        mkdir-p /etc/ssh/sshd_config.d : \
        upload /tmp/config/sshd.conf /etc/ssh/sshd_config.d/00-emulator.conf : \
        ln-sf /dev/null /etc/systemd/system/ssh.socket : \
        ln-sf /usr/lib/systemd/system/ssh.service /etc/systemd/system/multi-user.target.wants/ssh.service

FROM base AS qemu-builder

# Preserve signed magnetic readings in QEMU's LSM303DLHC QOM properties.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential pkg-config ninja-build python3-venv \
    libglib2.0-dev libpixman-1-dev libslirp-dev libfdt-dev zlib1g-dev patch && \
    rm -rf /var/lib/apt/lists/*
RUN curl -fL https://download.qemu.org/qemu-11.1.2.tar.xz -o /tmp/qemu.tar.xz && \
    echo "731b5681e4bb18be313231579b8efd0296c5b015fa36dc533874b639ba838016  /tmp/qemu.tar.xz" | sha256sum -c - && \
    mkdir /tmp/qemu && tar -xJf /tmp/qemu.tar.xz -C /tmp/qemu --strip-components=1 && \
    rm /tmp/qemu.tar.xz
COPY scripts/qemu-lsm303dlhc-signed.patch /tmp/qemu-signed.patch
RUN apt-get update && apt-get install -y --no-install-recommends python3-setuptools python3-wheel && \
    rm -rf /var/lib/apt/lists/*
RUN cd /tmp/qemu && patch -p1 < /tmp/qemu-signed.patch && \
    mkdir build && cd build && \
    ../configure --prefix=/usr --target-list=aarch64-softmmu --enable-slirp \
        --disable-docs --disable-tools --disable-guest-agent --disable-user \
        --disable-werror --disable-download && \
    ninja -j4 qemu-system-aarch64 && \
    install -D -s -m755 qemu-system-aarch64 /output/qemu-system-aarch64

FROM base

LABEL org.flight-studio.qemu-lsm-signed="1"
COPY --from=qemu-builder /output/qemu-system-aarch64 /usr/bin/qemu-system-aarch64

# Keep only the prepared disk and boot files in the distributed image.
COPY --from=prepare /opt/raspi-os/raspios.qcow2 \
    /opt/raspi-os/kernel8.img \
    /opt/raspi-os/bcm2711-rpi-4-b.dtb \
    /opt/raspi-os/initramfs8 \
    /opt/raspi-os/

COPY --chmod=755 scripts/emulator.sh /usr/local/bin/emulator
WORKDIR /work

ENTRYPOINT ["/usr/local/bin/emulator"]
