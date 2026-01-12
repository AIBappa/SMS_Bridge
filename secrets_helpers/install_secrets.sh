#!/usr/bin/env bash
# install_secrets.sh - safe installer for SMS Bridge secrets
# Usage: place the extracted secret files alongside this script and run as root:
#   sudo ./install_secrets.sh

set -euo pipefail

# Paths (edit if needed)
CLOUDFLARED_DIR=/etc/cloudflared
ANSIBLE_VAULT_DEST=~/

install_cloudflared_files() {
  echo "Installing cloudflared files to $CLOUDFLARED_DIR"
  sudo mkdir -p "$CLOUDFLARED_DIR"
  sudo cp -f ./config.yml "$CLOUDFLARED_DIR/config.yml"
  sudo cp -f ./credentials-file.json "$CLOUDFLARED_DIR/credentials-file.json"
  sudo chown root:root "$CLOUDFLARED_DIR/config.yml" "$CLOUDFLARED_DIR/credentials-file.json"
  sudo chmod 600 "$CLOUDFLARED_DIR/credentials-file.json"
  sudo chmod 640 "$CLOUDFLARED_DIR/config.yml"
  echo "cloudflared files installed"
}

install_vault() {
  echo "Placing Ansible vault file under $ANSIBLE_VAULT_DEST"
  cp -f ./vault.yml "$ANSIBLE_VAULT_DEST/vault.yml"
  chmod 600 "$ANSIBLE_VAULT_DEST/vault.yml"
  echo "vault file placed at $ANSIBLE_VAULT_DEST/vault.yml"
}

if [ "$EUID" -ne 0 ]; then
  echo "This script needs to run as root to set system paths and permissions. Re-run with sudo." >&2
  exit 1
fi

if [ -f ./config.yml ] && [ -f ./credentials-file.json ]; then
  install_cloudflared_files
else
  echo "cloudflared files not found in current directory. Extract the tarball and run this script next to the files." >&2
fi

if [ -f ./vault.yml ]; then
  install_vault
else
  echo "No vault.yml found; skipping vault install." >&2
fi

cat <<MSG
Done. Verify cloudflared service now points to $CLOUDFLARED_DIR/config.yml and restart the service if required:
  sudo systemctl restart cloudflared
MSG
