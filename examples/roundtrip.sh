#!/usr/bin/env bash
# End-to-end CLI round trip using the OFFLINE (null) backend, so it runs anywhere.
# For real name/org detection, drop --no-llm and make sure Ollama is running with
# qwen3.6:27b pulled.
set -euo pipefail
cd "$(dirname "$0")/.."

PY="$(command -v python3 || command -v python)"

tmp="$(mktemp -d)"
trap 'echo "(temp dir: $tmp)"' EXIT

cat > "$tmp/notes.txt" <<'EOF'
李雷在杭州的明远科技任 CTO，邮箱 li.lei@mingyuan.example，电话 13900008888。
EOF

echo "== 1. scrub (de-identify) =="
"$PY" -m vaultengine scrub "$tmp/notes.txt" -o "$tmp/out.txt" --no-llm

echo "== 2. sanitized text (safe to send to the cloud) =="
cat "$tmp/out.txt"; echo

echo "== 3. simulate a cloud reply that references a placeholder token =="
tok="$("$PY" - "$tmp/out.txt.map.json" <<'PY'
import json, sys
print(next(iter(json.load(open(sys.argv[1]))["tokens"])))
PY
)"
printf '{"insight": "%s 值得继续跟进"}\n' "$tok" > "$tmp/reply.json"
cat "$tmp/reply.json"

echo "== 4. rehydrate (real identities restored, locally) =="
"$PY" -m vaultengine rehydrate "$tmp/reply.json" --map "$tmp/out.txt.map.json"
echo
