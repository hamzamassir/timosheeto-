#!/usr/bin/env bash
set -euo pipefail
if [[ "${EUID}" -ne 0 ]]; then
  exec sudo bash "$0" "$@"
fi
REPO="/home/hamza/redmine-sync"
EXAMPLE="${REPO}/deploy/sudoers.d-redmine-sync.example"
TARGET="/etc/sudoers.d/redmine-sync"
install -o root -g root -m 440 "${EXAMPLE}" "${TARGET}"
visudo -cf "${TARGET}"
chmod +x "${REPO}/deploy/restart-services.sh" "${REPO}/deploy/deploy.sh" "${REPO}/deploy/install-systemd.sh"
echo "OK: ${TARGET}"
echo "Test: sudo -n -u hamza ${REPO}/deploy/restart-services.sh"
