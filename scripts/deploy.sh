#!/bin/bash
# Deploy the committed checkout to the VM as a new release. WORKSPACE_ADMIN is the administrator's SSH host alias.
set -euo pipefail
cd "$(dirname "$0")/.."
host=${WORKSPACE_ADMIN:-workspace-admin}
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  echo 'Commit tracked changes before deploying'; exit 1
fi
release_name=${1:-"release-$(date -u +%Y%m%dT%H%M%S)-$(git rev-parse --short HEAD)"}
[[ "$release_name" =~ ^[a-zA-Z0-9][a-zA-Z0-9.-]+$ ]]
release="/opt/workspace/releases/$release_name"
ssh "$host" "test ! -e '$release' && sudo mkdir -p '$release' && sudo chown \$(id -un): '$release'"
git archive HEAD | ssh "$host" "tar -xf - -C '$release'"
ssh "$host" "sudo bash '$release/infra/install.sh' '$release'"
printf '%s\n' "Deployed $(git rev-parse HEAD) to $release"
