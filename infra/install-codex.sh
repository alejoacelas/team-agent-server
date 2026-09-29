#!/bin/bash
# Install or update a root-owned Codex CLI for members who connect with the Codex app. Run as root.
set -euo pipefail
test "$(id -u)" = 0
version=${1:-latest}
case "$(uname -m)" in x86_64) arch=x86_64;; aarch64) arch=aarch64;; *) echo 'Unsupported CPU'; exit 1;; esac
asset="codex-$arch-unknown-linux-musl.tar.gz"
if [ "$version" = latest ]; then
  url="https://github.com/openai/codex/releases/latest/download/$asset"
else
  url="https://github.com/openai/codex/releases/download/rust-v$version/$asset"
fi
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
curl -fsSL "$url" -o "$work/codex.tar.gz"
tar -xzf "$work/codex.tar.gz" -C "$work"
install -m 755 -o root -g root "$work/codex-$arch-unknown-linux-musl" /usr/local/bin/codex
/usr/local/bin/codex --version
