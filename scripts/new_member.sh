#!/bin/bash
# Run by a server owner on their own computer: create a member's account and key, and write the two files to share with them.
# Usage: bash scripts/new_member.sh USERNAME WORK_EMAIL
set -euo pipefail
cd "$(dirname "$0")/.."
name=${1:?username, for example jane-doe}
email=${2:?work email}
host=${WORKSPACE_ADMIN:-workspace-admin}
[[ "$name" =~ ^[a-z][a-z0-9-]{1,30}$ ]] || { echo 'Username: lowercase letters, digits and dashes, starting with a letter'; exit 1; }
server=$(ssh -G "$host" | awk '/^hostname /{print $2}')
known=$(ssh -G "$host" | awk '/^userknownhostsfile /{print $2}')
known=${known/#\~/$HOME}
host_line=$(ssh-keygen -F "$server" -f "$known" | grep -v '^#' | head -1)
[ -n "$host_line" ] || { echo "No verified host key for $server in $known"; exit 1; }
out="members/$name"
[ ! -e "$out" ] || { echo "$out already exists"; exit 1; }
mkdir -p -m 700 "$out"
ssh-keygen -q -t ed25519 -N '' -C "team-agent-server $name" -f "$out/team-agent-server"
ssh "$host" "cat > '/tmp/$name.pub'" < "$out/team-agent-server.pub"
ssh "$host" "sudo bash /opt/workspace/current/infra/add-member.sh '$name' '$email' '/tmp/$name.pub' && rm '/tmp/$name.pub'"
rm "$out/team-agent-server.pub"

# The member pastes this into Terminal after downloading the key file to ~/Downloads.
{
  echo "mkdir -p ~/.ssh && chmod 700 ~/.ssh && test ! -e ~/.ssh/team-agent-server && mv ~/Downloads/team-agent-server ~/.ssh/team-agent-server && chmod 600 ~/.ssh/team-agent-server && printf '%s\n' '' 'Host team-agent-server' '  HostName $server' '  User $name' '  IdentityFile ~/.ssh/team-agent-server' '  IdentitiesOnly yes' '  UserKnownHostsFile ~/.ssh/team-agent-server-known-hosts' '  StrictHostKeyChecking yes' >> ~/.ssh/config && echo '$host_line' > ~/.ssh/team-agent-server-known-hosts && ssh team-agent-server true && echo 'Setup complete. Your workspace folder is /home/$name'"
} > "$out/setup-command.txt"
printf '%s\n' "Created $name." "Put $out/team-agent-server (attached as a file) and the text of $out/setup-command.txt in a password-manager item shared only with $email, then delete $out."
