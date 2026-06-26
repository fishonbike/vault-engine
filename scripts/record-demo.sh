#!/usr/bin/env bash
#
# Records the hero demo for the README.
#
#   asciinema rec demo.cast -c scripts/record-demo.sh
#   agg --idle-time-limit 1 demo.cast docs/demo.gif      # compress the model wait
#
# It runs the REAL pipeline against your local qwen3.6:27b, so names/orgs/places
# actually get caught. Pre-warm the model first (ollama run qwen3.6:27b hi) so the
# call is snappy; --idle-time-limit then squeezes any remaining pause in the GIF.
#
set -e
PY="$(command -v python3 || command -v python)"
cd "$(dirname "$0")/.."
pause() { sleep "${1:-1.4}"; }
say() { printf '\033[1;36m$ %s\033[0m\n' "$1"; }

tmp="$(mktemp -d)"
cat > "$tmp/notes.txt" <<'EOF'
林若曦是星澜资本的合伙人，在深圳见了字节跳动的陈大壮，聊了项目代号 Orca。
邮箱 lin@xinglan.vc，电话 13800002222。
EOF

clear
say "cat notes.txt"; pause
cat "$tmp/notes.txt"; pause 2

say "vault-engine scrub notes.txt -o safe.txt        # local qwen3.6:27b"; pause
"$PY" -m vaultengine scrub "$tmp/notes.txt" -o "$tmp/safe.txt" >/dev/null 2>&1 || true
pause 1

say "cat safe.txt        # this is what you send to the cloud"; pause
cat "$tmp/safe.txt"; pause 2

say "cat safe.txt.map.json        # stays on YOUR machine"; pause
cat "$tmp/safe.txt.map.json"; pause 2

say "vault-engine rehydrate cloud_reply.txt --map safe.txt.map.json"; pause
"$PY" -m vaultengine rehydrate "$tmp/safe.txt" --map "$tmp/safe.txt.map.json"
pause 2
printf '\n\033[1;32m✓ identities restored locally — the cloud never saw them\033[0m\n'
pause 2
rm -rf "$tmp"
