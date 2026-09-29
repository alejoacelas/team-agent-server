#!/bin/bash
# Run once as root after first boot: move /home onto the encrypted volume, then harden the host.
# Idempotent. WORKSPACE_VOLUME and WORKSPACE_HOME_TARGET exist only for testing on another path.
set -euo pipefail
test "$(id -u)" = 0
volume=${WORKSPACE_VOLUME:-/dev/disk/by-id/scsi-0DO_Volume_workspace-home}
target=${WORKSPACE_HOME_TARGET:-/home}
export DEBIAN_FRONTEND=noninteractive

# 1. Member homes live on the DigitalOcean volume, which is encrypted at rest; the Droplet disk is not.
if ! test -b "$volume"; then
  echo "Volume $volume is missing: attach the workspace-home volume before continuing"; exit 1
fi
if ! blkid "$volume" >/dev/null 2>&1; then
  mkfs.ext4 -q -L workspace-home "$volume"
fi
if [ "$(blkid -s TYPE -o value "$volume")" != ext4 ]; then
  echo "Volume has a non-ext4 filesystem; recreate it with manual formatting"; exit 1
fi
e2label "$volume" workspace-home
uuid=$(blkid -s UUID -o value "$volume")
if ! mountpoint -q "$target"; then
  staging=$(mktemp -d)
  mount "$volume" "$staging"
  rsync -aHAX "$target"/ "$staging"/
  umount "$staging"; rmdir "$staging"
  # No nofail: if the volume is absent the host should stop rather than write homes to the unencrypted disk.
  grep -q "UUID=$uuid" /etc/fstab || printf 'UUID=%s %s ext4 defaults,noatime,x-systemd.device-timeout=5min 0 2\n' "$uuid" "$target" >> /etc/fstab
  systemctl daemon-reload
  mount "$target"
fi
if [ "$(findmnt -rn -o UUID --mountpoint "$target")" != "$uuid" ]; then
  echo "$target is mounted from a different device; expected the workspace-home volume"; exit 1
fi
[ "$target" = /home ] || { echo "Test mount verified at $target"; exit 0; }

# 2. Temporary files stay in memory, so agent scratch files never reach the unencrypted disk.
if [ -e /usr/share/systemd/tmp.mount ] && [ ! -e /etc/systemd/system/tmp.mount ]; then
  cp /usr/share/systemd/tmp.mount /etc/systemd/system/tmp.mount
  systemctl daemon-reload
  systemctl enable tmp.mount
  echo 'tmp.mount enabled; /tmp becomes memory-backed after the next reboot'
fi

# 3. Members cannot see each other's processes or command lines.
groupadd -f workspace-admins
groupadd -f workspace-users
usermod -aG workspace-admins workspace-admin
if ! grep -qE '^proc\s+/proc\s' /etc/fstab; then
  printf 'proc /proc proc defaults,hidepid=invisible,gid=workspace-admins 0 0\n' >> /etc/fstab
fi
mount -o remount,hidepid=invisible,gid="$(getent group workspace-admins | cut -d: -f3)" /proc

# 4. SSH: keys only, no root, and only the two workspace groups may log in.
cat > /etc/ssh/sshd_config.d/00-workspace.conf <<'SSH'
PubkeyAuthentication yes
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
X11Forwarding no
AllowGroups workspace-admins workspace-users
SSH
for user in $(getent passwd | awk -F: '$6 ~ "^/home/" {print $1}'); do
  if [ -e "/home/$user/.config/workspace/config.json" ]; then usermod -aG workspace-users "$user"; fi
done
sshd -t
systemctl reload ssh

# 5. Security updates install nightly and reboot at 04:00 server time (UTC unless you change it) when a kernel update needs it.
apt-get install -y -qq unattended-upgrades restic
timedatectl set-timezone ${WORKSPACE_TIMEZONE:-UTC}
cat > /etc/apt/apt.conf.d/52workspace-reboot <<'APT'
Unattended-Upgrade::Automatic-Reboot "true";
Unattended-Upgrade::Automatic-Reboot-Time "04:00";
APT
printf '%s\n' 'Host setup complete: encrypted /home, private processes, restricted SSH, automatic security updates.'
