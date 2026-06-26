#!/usr/bin/env python3
"""Round-trip demo — runs with zero setup (offline 'null' provider).

    python examples/demo.py

Swap ``provider='null'`` for ``provider='ollama'`` (with Ollama running and
qwen3.6:27b pulled) to see person/org/location names get caught too — the null
provider only exercises the deterministic PII layer.
"""

from __future__ import annotations

import json

from vaultengine import Config, deidentify, rehydrate

TEXT = (
    "苏曼在「云图科技」负责增长，邮箱 grow@yuntu.example，手机 13700001234。\n"
    "她和 P-7 上周在线下见过面。"
)


def main() -> None:
    cfg = Config(provider="null", policy="balanced")   # offline, no model
    result = deidentify(TEXT, cfg)

    print("原文 ──────────────────────────────")
    print(TEXT)
    print("\n出云版（脱敏后，可发给云端 AI）────────")
    print(result.text)

    print("\n反向映射（只存本地，切勿出云）─────────")
    print(json.dumps(result.map["tokens"], ensure_ascii=False, indent=2))

    # The cloud replies using the placeholder tokens; we restore real identities.
    a_token = next(iter(result.map["tokens"]), None)
    if a_token:
        cloud_reply = {"insight": f"{a_token} 值得继续跟进"}
        print("\n云端回复（含代号）→ 回填真实身份 ──────")
        print(json.dumps(rehydrate(cloud_reply, result.vault), ensure_ascii=False))

    print("\n报告摘要 ──────────────────────────")
    print(result.report.summary())


if __name__ == "__main__":
    main()
