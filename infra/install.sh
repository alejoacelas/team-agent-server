#!/bin/bash
# Run as root on the VM after placing the release in /opt/workspace/releases/ID.
set -euo pipefail
release=${1:?release directory required}
case "$release" in /opt/workspace/releases/*) ;; *) echo 'Unexpected release path'; exit 1;; esac
test "$(id -u)" = 0
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3-venv poppler-utils restic sqlite3
install -d -m 755 /etc/workspace
python3 -m venv "$release/venv"
"$release/venv/bin/pip" -q install -r "$release/requirements.lock"
"$release/venv/bin/pip" -q install --no-deps "$release"
"$release/venv/bin/workspace-import" --help >/dev/null
chown -R root:root "$release"
chmod -R go-w "$release"
ln -sfn "$release" /opt/workspace/current.next
mv -Tf /opt/workspace/current.next /opt/workspace/current
ln -sfn /opt/workspace/current/venv/bin/workspace-import /usr/local/bin/workspace-import
install -m 644 "$release/infra/workspace-refresh@.service" /etc/systemd/system/workspace-refresh@.service
install -m 644 "$release/infra/workspace-refresh@.timer" /etc/systemd/system/workspace-refresh@.timer
install -m 644 "$release/infra/workspace-inventory.service" /etc/systemd/system/workspace-inventory.service
install -m 644 "$release/infra/workspace-inventory.timer" /etc/systemd/system/workspace-inventory.timer
install -m 644 "$release/infra/workspace-backup.service" /etc/systemd/system/workspace-backup.service
install -m 644 "$release/infra/workspace-backup.timer" /etc/systemd/system/workspace-backup.timer
systemctl daemon-reload
systemctl enable --now workspace-inventory.timer
printf '%s\n' 'Installed. Backups start once /etc/workspace/backup.env exists and workspace-backup.timer is enabled.'
