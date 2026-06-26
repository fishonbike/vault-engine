"""Risk report — an honest account of what was redacted and what may remain.

The report is deterministic (no timestamps) so it is easy to test and diff. It
makes the failure modes loud: if the model layer didn't run, or the critic found
residual leakage, that is stated at the top, not buried.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from .mapping import Vault
from .spans import CAT_PERSON, CATEGORY_LABELS, Span


@dataclass
class Report:
    policy: str
    provider_name: str
    model: str
    llm_requested: bool
    llm_ok: bool
    critic_ok: bool
    error: str
    category_counts: Dict[str, int]
    token_total: int
    person_total: int
    occurrence_total: int
    regex_total: int
    llm_total: int
    residual: List[Dict[str, str]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def summary(self) -> str:
        head = (f"{self.token_total} 个实体已假名化"
                f"（{self.person_total} 人 / 共 {self.occurrence_total} 处）"
                f"｜policy={self.policy}｜{self.provider_name}:{self.model}")
        if self.warnings:
            head += f"｜⚠️ {len(self.warnings)} 条告警"
        return head

    def to_markdown(self) -> str:
        lines = ["# vault-engine 脱敏报告", ""]
        if self.warnings:
            lines.append("## ⚠️ 告警")
            lines += [f"- {w}" for w in self.warnings]
            lines.append("")
        lines += [
            "## 概况",
            f"- 力度 policy：`{self.policy}`",
            f"- 检测模型：`{self.provider_name}` / `{self.model}`"
            + ("（**未成功运行**）" if self.llm_requested and not self.llm_ok else ""),
            f"- 假名化实体：**{self.token_total}** 个（其中人物 {self.person_total} 个），"
            f"全文替换 {self.occurrence_total} 处",
            f"- 检测来源：正则命中 {self.regex_total} 项，模型命中 {self.llm_total} 项",
            "",
            "## 分类统计",
        ]
        if self.category_counts:
            for cat, n in sorted(self.category_counts.items(),
                                 key=lambda kv: (-kv[1], kv[0])):
                lines.append(f"- {CATEGORY_LABELS.get(cat, cat)}：{n}")
        else:
            lines.append("-（无）")
        lines.append("")

        lines.append("## 残留风险复审（critic）")
        if not self.llm_requested:
            lines.append("- 未运行（regex-only 模式）。")
        elif not self.critic_ok:
            lines.append("- 复审请求失败，未获结果。")
        elif not self.residual:
            lines.append("- 未发现明显残留。（仍非绝对保证，见下方说明。）")
        else:
            for r in self.residual:
                lines.append(f"- `{r.get('quote','')}` —— {r.get('why','')}")
        lines += [
            "",
            "## 说明（务必阅读）",
            "- 模型检测属**尽力而为**，非身份不可识别的数学保证；越罕见的语境组合越可能反推。",
            "- 反向映射表（`*.map.json`）就是身份本身，**只存本地、严禁出云、勿入库提交**。",
            "",
        ]
        return "\n".join(lines)


def build_report(vault: Vault, spans: List[Span], residual: List[Dict[str, str]],
                 llm_requested: bool, llm_ok: bool, critic_ok: bool, policy: str,
                 provider_name: str, model: str, error: str = "") -> Report:
    category_counts: Dict[str, int] = {}
    person_total = 0
    occurrence_total = 0
    for entry in vault.tokens.values():
        cat = entry.get("category", "other")
        category_counts[cat] = category_counts.get(cat, 0) + 1
        occurrence_total += int(entry.get("count", 0))
        if cat == CAT_PERSON:
            person_total += 1

    regex_total = sum(1 for s in spans if s.source.startswith("regex"))
    llm_total = sum(1 for s in spans if s.source == "llm")

    warnings: List[str] = []
    if llm_requested and not llm_ok:
        warnings.append(
            "模型检测层未成功运行，本次仅有正则兜底——**输出很可能脱敏不足，请勿直接出云**。"
            + (f"（{error}）" if error else ""))
    if not llm_requested:
        warnings.append("regex-only 模式：未启用模型语义检测，仅覆盖结构化 PII，"
                        "人名/机构/地点等需模型才能识别的项可能残留。")
    if llm_requested and llm_ok and not critic_ok:
        warnings.append("残留风险复审（critic）调用失败，未能二次校验。")
    if residual:
        warnings.append(f"复审发现 {len(residual)} 处疑似残留身份信息，请见报告末尾逐条核对。")

    # light re-identification heuristic: a lone person plus specific anchors
    if person_total == 1 and (category_counts.get("org") or
                              category_counts.get("location") or
                              category_counts.get("role")):
        warnings.append("全文仅 1 个人物且伴随机构/地点/职务代号——"
                        "即便假名化，独特语境组合仍可能缩小身份范围，注意力度档位。")

    return Report(policy=policy, provider_name=provider_name, model=model,
                  llm_requested=llm_requested, llm_ok=llm_ok, critic_ok=critic_ok,
                  error=error, category_counts=category_counts,
                  token_total=len(vault.tokens), person_total=person_total,
                  occurrence_total=occurrence_total, regex_total=regex_total,
                  llm_total=llm_total, residual=residual, warnings=warnings)
