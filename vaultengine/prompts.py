"""Prompt templates for LLM-backed detection and residual-risk critique.

The model is used as a *detector only*: it returns spans to redact, never a
rewritten document. That keeps the transform deterministic (the Vault does the
substitution) and reversible, and removes any chance of the model hallucinating
new content into the text that ships to the cloud.
"""

from __future__ import annotations

# Closed category vocabulary handed to the model (mirrors spans.CATEGORIES).
_CATEGORIES = ("person, org, location, role, project, date, contact, id, other")

_DETECT_ZH = """你是一个隐私脱敏前置检测器。下面的文本即将被发送给云端 AI 做分析，
在发送前必须找出其中一切可能暴露真实身份的片段。

只做"标注"，不要改写、不要总结、不要翻译原文。

请输出一个 JSON 数组，每个元素标注一个需要脱敏的片段：
[{{"surface": "原文中一字不差的子串", "category": "%s",
  "aliases": ["指向同一对象的其他写法，没有就空数组"], "confidence": 0.0到1.0}}]

类别说明：
- person  人名、昵称、化名、称呼（"老张""王总"也算）——**每一个具体的人都要标出**
- org     公司、机构、学校、团队、基金、政府部门
- location 具体地点、地址、园区、楼宇、城市级以下的精确位置
- role    能缩小身份范围的独特职务/头衔（"XX公司CTO""红杉合伙人"）
- project 项目代号、产品名、内部代称
- date    能定位到具体事件的日期/时间
- contact 邮箱、电话、社交账号、URL
- id      证件号、卡号、账号等标识符
- other   其他罕见但可定位身份的线索

规则：
1. surface 必须是原文里真实出现的精确子串，便于程序做字面替换。
2. 同一个人/机构的多种写法，用 aliases 归并到同一条，便于全篇用同一代号。
3. 文本里已经形如 P-1 / P-n2 / ORG_3 的代号是**已脱敏占位符，跳过，不要标注**。
4. 拿不准就降低 confidence；确实没有任何可标注片段就返回 []。
5. **只输出 JSON 数组本身，不要任何解释文字、不要 markdown 代码围栏。**

文本如下：
---
%s
---"""

_DETECT_EN = """You are a pre-egress privacy detector. The text below is about to
be sent to a cloud AI for analysis. Before it leaves, find every span that could
reveal a real identity. Only annotate — never rewrite, summarize, or translate.

Output a JSON array; each element marks one span to redact:
[{{"surface": "exact substring from the text", "category": "%s",
  "aliases": ["other spellings of the same entity, [] if none"], "confidence": 0.0-1.0}}]

Rules: surface must be an exact substring; group aliases of one entity onto a
single record; skip strings already shaped like placeholders (P-1, ORG_3, …);
lower confidence when unsure; return [] if nothing applies; output ONLY the JSON
array, no prose, no code fences.

Text:
---
%s
---"""

_CRITIC_ZH = """下面这段文本已经做过一轮身份脱敏（真实信息被替换成 P-1 / ORG_2 这样的代号）。
请以攻击者视角复查：是否还残留任何可以反推真实身份的信息？
包括漏网的人名/机构/地点、能唯一定位身份的"罕见属性组合"（如 某市+某独特职务+某事件）。

输出 JSON 数组，每条一个残留风险：
[{{"quote": "文本中仍然存在的可疑片段", "category": "%s", "why": "为什么它可能暴露身份"}}]

只报真正可能定位到具体个人/机构的；纯代号和泛泛信息不要报。没有就返回 []。
**只输出 JSON 数组，不要解释、不要代码围栏。**

文本如下：
---
%s
---"""

_CRITIC_EN = """The text below was already de-identified (real info replaced by
codes like P-1 / ORG_2). Re-read it as an attacker: is any information still
present that could re-identify a real person or organization — a missed name, or
a rare quasi-identifier combination (city + unique role + event)?

Output a JSON array, one residual risk each:
[{{"quote": "suspicious span still present", "category": "%s", "why": "why it may leak identity"}}]

Report only genuine re-identification risks; ignore codes and generic facts.
Return [] if none. Output ONLY the JSON array, no prose, no code fences.

Text:
---
%s
---"""


def detect_prompt(text: str, locale: str = "zh") -> str:
    tpl = _DETECT_ZH if locale == "zh" else _DETECT_EN
    return tpl % (_CATEGORIES, text)


def critic_prompt(text: str, locale: str = "zh") -> str:
    tpl = _CRITIC_ZH if locale == "zh" else _CRITIC_EN
    return tpl % (_CATEGORIES, text)
