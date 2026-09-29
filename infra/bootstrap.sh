#!/bin/bash
# DigitalOcean first-boot script. Selected Droplet SSH key supplies admin access.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
# Refuse to disable recovery access if DigitalOcean did not inject a public key.
test -s /root/.ssh/authorized_keys
apt-get update
apt-get install -y ca-certificates curl git jq python3 python3-venv ripgrep rsync sqlite3 tmux ufw unattended-upgrades
id workspace-admin >/dev/null 2>&1 || useradd --create-home --shell /bin/bash workspace-admin
passwd -l workspace-admin
chmod 700 /home/workspace-admin
install -d -m 700 -o workspace-admin -g workspace-admin /home/workspace-admin/.ssh
install -m 600 -o workspace-admin -g workspace-admin /root/.ssh/authorized_keys /home/workspace-admin/.ssh/authorized_keys
printf '%s\n' 'workspace-admin ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/workspace-admin
chmod 440 /etc/sudoers.d/workspace-admin
visudo -cf /etc/sudoers.d/workspace-admin
install -d -m 700 -o workspace-admin -g workspace-admin /srv/workspace
cat > /etc/ssh/sshd_config.d/00-workspace.conf <<'SSH'
PubkeyAuthentication yes
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin prohibit-password
X11Forwarding no
SSH
# Root key login remains available until a separate admin connection is tested.
sshd -t
systemctl reload ssh
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp comment 'SSH key authentication only'
ufw --force enable
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'APT'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT
install -d -m 755 /var/lib/workspace
printf '%s\n' 'Bootstrap complete; source imports and member access are not configured.' > /var/lib/workspace/bootstrap-complete
