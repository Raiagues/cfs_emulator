#!/usr/bin/env bash
set -e

if ! command -v docker >/dev/null 2>&1; then
    echo "Installing Docker..."
    sudo apt-get update
    sudo apt-get install -y docker.io
fi

if docker info >/dev/null 2>&1; then
    echo "Docker is ready."
    exit 0
fi

if ! sudo docker info >/dev/null 2>&1; then
    sudo systemctl enable --now docker
fi

sudo groupadd -f docker
sudo usermod -aG docker "$(id -un)"

echo "Setup completed. Log out and log back in to use Docker."
