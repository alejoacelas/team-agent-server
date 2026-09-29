#!/bin/bash
set -euo pipefail
name=${1:?username}
email=${2:?email}
key_file=${3:?public-key file}
[[ "$name" =~ ^[a-z][a-z0-9-]{1,30}$ ]]
[[ "$email" =~ ^[a-zA-Z0-9._+%-]+@[a-zA-Z0-9.-]+$ ]]
test "$(id -u)" = 0
ssh-keygen -lf "$key_file" >/dev/null
if ! id "$name" >/dev/null 2>&1; then
  useradd --create-home --shell /bin/bash "$name"
fi
test "$(getent passwd "$name" | cut -d: -f6)" = "/home/$name"
if id -nG "$name" | tr ' ' '\n' | grep -qx sudo; then
  echo 'Refusing member in sudo group'; exit 1
fi
passwd -l "$name" >/dev/null
usermod -aG workspace-users "$name"
chmod 700 "/home/$name"
install -d -m 700 -o "$name" -g "$name" "/home/$name/.ssh"
auth="/home/$name/.ssh/authorized_keys"
if [ ! -e "$auth" ]; then
  install -m 600 -o "$name" -g "$name" "$key_file" "$auth"
elif ! cmp -s "$key_file" "$auth"; then
  echo 'Existing SSH keys differ; preserve them and review rotation explicitly'; exit 1
fi
sudo -H -u "$name" workspace-import init --email "$email"
# Agents load these files automatically; they point at the installed release, so deployments update them.
guide=/opt/workspace/current/docs/member-start.md
install -d -m 700 -o "$name" -g "$name" "/home/$name/.claude" "/home/$name/.codex"
for link in AGENTS.md CLAUDE.md .claude/CLAUDE.md .codex/AGENTS.md; do
  # Never replace a file the member wrote themselves.
  if [ ! -e "/home/$name/$link" ] || [ -L "/home/$name/$link" ]; then
    ln -sfn "$guide" "/home/$name/$link"
    chown -h "$name:$name" "/home/$name/$link"
  fi
done
# The monthly refresh only touches sources the member has enabled, so it is safe to start now.
systemctl enable --now "workspace-refresh@$name.timer"
printf '%s\n' "Member ready: $name. Send them the member guide with their username."
