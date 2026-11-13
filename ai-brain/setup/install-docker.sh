#!/usr/bin/env bash
# Install Docker Engine, CLI, buildx and the compose plugin from Docker's apt repo, no Docker Desktop.
# Ubuntu on WSL2 with systemd. Run as your own user: the script calls sudo itself.
# Steps follow https://docs.docker.com/engine/install/ubuntu/.
set -euo pipefail
trap 'echo "install-docker: failed at line $LINENO" >&2' ERR

if [ "$(id -u)" -eq 0 ]; then
  echo "Run this as your own user, not with sudo: it calls sudo where it needs to." >&2
  exit 1
fi

. /etc/os-release
if [ "${ID:-}" != "ubuntu" ]; then
  echo "Ubuntu only (found: ${ID:-unknown})." >&2
  exit 1
fi
if [ "$(ps -p 1 -o comm=)" != "systemd" ]; then
  echo "systemd is not running. Set '[boot] systemd=true' in /etc/wsl.conf, run 'wsl --shutdown' from Windows, then rerun." >&2
  exit 1
fi

me="$(id -un)"
codename="${UBUNTU_CODENAME:-$VERSION_CODENAME}"
arch="$(dpkg --print-architecture)"

echo "==> 1/5 Remove conflicting packages"
conflicts="$(dpkg --get-selections docker.io docker-compose docker-compose-v2 docker-doc docker-buildx podman-docker containerd runc 2>/dev/null | cut -f1 || true)"
if [ -n "$conflicts" ]; then
  # shellcheck disable=SC2086 # one argument per package name
  sudo apt-get remove $conflicts
else
  echo "    none installed"
fi

echo "==> 2/5 Add Docker's apt repository (${codename}, ${arch})"
sudo apt-get update
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
sudo tee /etc/apt/sources.list.d/docker.sources >/dev/null <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: ${codename}
Components: stable
Architectures: ${arch}
Signed-By: /etc/apt/keyrings/docker.asc
EOF
sudo apt-get update

echo "==> 3/5 Install Docker Engine, CLI, buildx and compose"
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

echo "==> 4/5 Start the service and run hello-world"
sudo systemctl enable --now containerd docker
if ! systemctl is-active --quiet docker; then
  echo "docker.service did not start. See: sudo journalctl -u docker -n 50" >&2
  echo "On WSL, iptables errors there usually clear with:" >&2
  echo "  sudo update-alternatives --set iptables /usr/sbin/iptables-legacy && sudo systemctl restart docker" >&2
  exit 1
fi
sudo docker run --rm hello-world

echo "==> 5/5 Optional: run docker without sudo"
echo "    Members of the docker group get root-equivalent access to this machine."
read -r -p "    Add ${me} to the docker group? [y/N] " answer || answer=""
if [[ "${answer}" =~ ^[Yy]$ ]]; then
  sudo usermod -aG docker "${me}"
  echo "    Added. Run 'newgrp docker' in this shell, or 'wsl --shutdown' from Windows and reopen the terminal."
fi

docker --version
docker compose version
echo "Docker Engine installed."
