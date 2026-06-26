"""Command-line interface.

    vault-engine scrub  INFILE [-o OUT] [--map MAP] [--report REPORT] ...
    vault-engine rehydrate INFILE --map MAP [-o OUT]
    vault-engine providers
    vault-engine models
    vault-engine version

Use ``-`` for INFILE/OUT to read stdin / write stdout.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import List, Optional

from . import __version__, formats
from .config import POLICIES, Config
from .mapping import Vault
from .pipeline import deidentify, rehydrate
from .providers import available
from .providers.ollama import DEFAULT_ENDPOINT, installed_models

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_DEGRADED = 3   # ran, but a requested protection layer did not (under-redacted)

DEFAULT_CLIP_MAP = os.path.join(os.path.expanduser("~"), ".vault-engine",
                                "clip.map.json")


def _read(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _write(path: str, data: str) -> None:
    if path == "-":
        sys.stdout.write(data)
        return
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(data)


def _default_out(infile: str) -> str:
    if infile == "-":
        return "-"
    stem, ext = os.path.splitext(infile)
    return f"{stem}.scrubbed{ext or '.txt'}"


def _config_from(args: argparse.Namespace) -> Config:
    overrides = {
        "provider": args.provider, "model": args.model,
        "endpoint": args.endpoint, "api_key": args.api_key,
        "policy": args.policy, "locale": args.locale,
        "use_llm": (False if args.no_llm else None),
        "critic": (False if args.no_critic else None),
        "scrub_fenced": getattr(args, "scrub_fenced", None),
    }
    return Config.load(path=args.config,
                       overrides={k: v for k, v in overrides.items()
                                  if v is not None})


def cmd_scrub(args: argparse.Namespace) -> int:
    text = _read(args.infile)
    config = _config_from(args)
    segs = formats.segment(text, args.format, scrub_fenced=config.scrub_fenced)
    result = deidentify(text, config, segments=segs)

    out = args.out or _default_out(args.infile)
    _write(out, result.text)

    # reverse map — local only, never for the cloud
    if not args.one_way:
        map_path = args.map or (
            "vault.map.json" if out == "-" else out + ".map.json")
        if map_path != "-":
            result.vault.save(map_path)
        else:
            sys.stdout.write("\n" + json.dumps(result.map, ensure_ascii=False))

    if args.report:
        _write(args.report, result.report.to_markdown())

    # always tell the human what happened (on stderr so stdout stays clean)
    print(result.report.summary(), file=sys.stderr)
    for w in result.report.warnings:
        print("  ⚠️ " + w, file=sys.stderr)
    if not args.one_way and out != "-":
        print(f"  脱敏文本 → {out}", file=sys.stderr)
        print(f"  反向映射 → {map_path}  （本地保存，切勿出云/入库）", file=sys.stderr)

    if not result.safe and not args.allow_degraded:
        print("✗ 请求的模型检测层未运行；输出可能脱敏不足。确认无碍可加 "
              "--allow-degraded。", file=sys.stderr)
        return EXIT_DEGRADED
    return EXIT_OK


def cmd_rehydrate(args: argparse.Namespace) -> int:
    payload = _read(args.infile)
    vault = Vault.load(args.map)
    try:                                   # structured reply: rehydrate in place
        obj = json.loads(payload)
        restored = json.dumps(rehydrate(obj, vault), ensure_ascii=False, indent=2)
    except json.JSONDecodeError:           # plain text reply
        restored = rehydrate(payload, vault)
    _write(args.out or "-", restored)
    if args.out and args.out != "-":
        print(f"已回填真实身份 → {args.out}", file=sys.stderr)
    return EXIT_OK


def cmd_clip(args: argparse.Namespace) -> int:
    """Scrub (or rehydrate) the clipboard in place — the paste-into-ChatGPT hook."""
    from . import clipboard
    map_path = args.map or DEFAULT_CLIP_MAP
    try:
        text = clipboard.read_clipboard()
    except clipboard.ClipboardError as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return EXIT_ERROR
    if not text.strip():
        print("剪贴板为空。", file=sys.stderr)
        return EXIT_ERROR

    if args.rehydrate:
        vault = Vault.load(map_path)
        try:
            restored = json.dumps(rehydrate(json.loads(text), vault),
                                  ensure_ascii=False, indent=2)
        except json.JSONDecodeError:
            restored = rehydrate(text, vault)
        clipboard.write_clipboard(restored)
        print("✓ 剪贴板已用本地映射还原为真实身份。", file=sys.stderr)
        return EXIT_OK

    config = _config_from(args)
    segs = formats.segment(text, args.format, scrub_fenced=config.scrub_fenced)
    result = deidentify(text, config, segments=segs)
    clipboard.write_clipboard(result.text)
    if not args.one_way:
        os.makedirs(os.path.dirname(map_path), exist_ok=True)
        result.vault.save(map_path)

    print(result.report.summary(), file=sys.stderr)
    for w in result.report.warnings:
        print("  ⚠️ " + w, file=sys.stderr)
    print("✓ 剪贴板已脱敏，可直接粘贴给云端 AI。", file=sys.stderr)
    if not args.one_way:
        print(f"  反向映射 → {map_path}（本地保存，勿出云）", file=sys.stderr)
        print("  云端回复贴回剪贴板后，用 `vault-engine clip --rehydrate` 还原。",
              file=sys.stderr)
    if not result.safe and not args.allow_degraded:
        print("✗ 模型检测层未运行，可能脱敏不足（--allow-degraded 忽略）。", file=sys.stderr)
        return EXIT_DEGRADED
    return EXIT_OK


def cmd_providers(_args: argparse.Namespace) -> int:
    print("可用 provider：")
    notes = {"ollama": "本地 Ollama（默认，原文不出本机）",
             "openai-compat": "OpenAI 兼容端点（⚠️ 原文会出本机，默认不用）",
             "null": "纯正则离线（无模型，仅兜底）"}
    for name in available():
        print(f"  - {name:14s} {notes.get(name, '')}")
    return EXIT_OK


def cmd_models(args: argparse.Namespace) -> int:
    endpoint = args.endpoint or DEFAULT_ENDPOINT
    models = installed_models(endpoint)
    if not models:
        print(f"未能从 {endpoint} 获取模型列表（Ollama 未运行？）", file=sys.stderr)
        return EXIT_ERROR
    print(f"{endpoint} 已安装模型：")
    for m in models:
        print(f"  - {m}")
    return EXIT_OK


def cmd_version(_args: argparse.Namespace) -> int:
    print(f"vault-engine {__version__}")
    return EXIT_OK


def _add_model_flags(p: argparse.ArgumentParser) -> None:
    p.add_argument("--provider", help="ollama(默认) / openai-compat / null")
    p.add_argument("--model", help="模型 tag，默认 qwen3.6:27b")
    p.add_argument("--endpoint", help="provider 端点 URL")
    p.add_argument("--api-key", dest="api_key", help="远程端点的 API key")
    p.add_argument("--config", help="JSON 配置文件路径（亦读 VAULT_* 环境变量）")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vault-engine",
        description="出云前的身份脱敏：本地检测 + 一致化假名 + 可逆回路（默认本地模型）。")
    parser.add_argument("--version", action="version",
                        version=f"vault-engine {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    s = sub.add_parser("scrub", help="脱敏一个文件/标准输入")
    s.add_argument("infile", help="输入文件（- 表示 stdin）")
    s.add_argument("-o", "--out", help="脱敏输出（默认 <name>.scrubbed.<ext>；- 表示 stdout）")
    s.add_argument("--map", help="反向映射保存路径（默认 <out>.map.json）")
    s.add_argument("--report", help="把完整风险报告写到此路径")
    s.add_argument("--format", choices=formats.FORMATS, default=formats.AUTO,
                   help="plain / markdown(保护 ``` 代码块) / auto(默认)")
    s.add_argument("--scrub-fenced", action="store_true",
                   help="同时脱敏 ``` 代码块内部的代码/数据")
    s.add_argument("--policy", choices=POLICIES, help="脱敏力度，默认 balanced")
    s.add_argument("--locale", help="zh(默认) / en：正则集与 prompt 语言")
    s.add_argument("--no-llm", action="store_true", help="仅正则、不调模型（离线兜底）")
    s.add_argument("--no-critic", action="store_true", help="跳过残留风险复审")
    s.add_argument("--one-way", action="store_true",
                   help="单向发布模式：不产出反向映射（不可回填）")
    s.add_argument("--allow-degraded", action="store_true",
                   help="即便模型层未运行也以 0 退出")
    _add_model_flags(s)
    s.set_defaults(func=cmd_scrub)

    r = sub.add_parser("rehydrate", help="用映射把云端回复里的代号还原成真实身份")
    r.add_argument("infile", help="云端回复（- 表示 stdin）")
    r.add_argument("--map", required=True, help="scrub 时产出的 *.map.json")
    r.add_argument("-o", "--out", help="输出路径（默认 stdout）")
    r.set_defaults(func=cmd_rehydrate)

    c = sub.add_parser("clip", help="脱敏剪贴板内容（贴进 ChatGPT 前一键洗）")
    c.add_argument("--rehydrate", action="store_true",
                   help="反向：用映射把剪贴板里的代号还原成真实身份")
    c.add_argument("--map", help=f"映射路径（默认 {DEFAULT_CLIP_MAP}）")
    c.add_argument("--format", choices=formats.FORMATS, default=formats.AUTO)
    c.add_argument("--scrub-fenced", action="store_true",
                   help="同时脱敏 ``` 代码块内部的代码/数据")
    c.add_argument("--policy", choices=POLICIES, help="脱敏力度，默认 balanced")
    c.add_argument("--locale", help="zh(默认) / en")
    c.add_argument("--no-llm", action="store_true", help="仅正则、不调模型")
    c.add_argument("--no-critic", action="store_true", help="跳过残留风险复审")
    c.add_argument("--one-way", action="store_true", help="不产出反向映射")
    c.add_argument("--allow-degraded", action="store_true",
                   help="即便模型层未运行也以 0 退出")
    _add_model_flags(c)
    c.set_defaults(func=cmd_clip)

    sub.add_parser("providers", help="列出可用大模型 provider").set_defaults(
        func=cmd_providers)

    m = sub.add_parser("models", help="列出本地 Ollama 已安装模型")
    m.add_argument("--endpoint", help="Ollama 端点，默认 http://localhost:11434")
    m.set_defaults(func=cmd_models)

    sub.add_parser("version", help="打印版本").set_defaults(func=cmd_version)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (OSError, ValueError) as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
