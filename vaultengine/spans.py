"""Span model and category vocabulary.

A Span is a contiguous stretch of the source text that carries identity. Every
detector (deterministic regex or LLM) emits Spans; the pipeline merges them and
the Vault turns each distinct surface into a stable placeholder token.

Spans never travel to a cloud model — only the sanitized text does. The category
of a span decides which token namespace it lands in (see ``mapping.py``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

# --- category vocabulary --------------------------------------------------
# Kept small and closed on purpose: a fixed set is what lets the placeholder
# token itself carry coarse, non-identifying structure ("ORG_1 hired PERSON_2").
CAT_PERSON = "person"
CAT_ORG = "org"
CAT_LOCATION = "location"
CAT_ROLE = "role"
CAT_PROJECT = "project"
CAT_DATE = "date"
CAT_CONTACT = "contact"  # email / phone / url / social handle (sub-kind in `note`)
CAT_ID = "id"            # gov id, card, account, ip, crypto address …
CAT_OTHER = "other"

CATEGORIES = (
    CAT_PERSON, CAT_ORG, CAT_LOCATION, CAT_ROLE,
    CAT_PROJECT, CAT_DATE, CAT_CONTACT, CAT_ID, CAT_OTHER,
)

# Human-facing labels for the risk report.
CATEGORY_LABELS = {
    CAT_PERSON: "人物 / person",
    CAT_ORG: "机构 / organization",
    CAT_LOCATION: "地点 / location",
    CAT_ROLE: "职务角色 / role",
    CAT_PROJECT: "项目产品 / project",
    CAT_DATE: "日期 / date",
    CAT_CONTACT: "联系方式 / contact",
    CAT_ID: "证件账号 / identifier",
    CAT_OTHER: "其他标识 / other",
}


def normalize_category(value: str) -> str:
    """Map a model's free-form category guess onto the closed vocabulary."""
    if not value:
        return CAT_OTHER
    v = str(value).strip().lower()
    if v in CATEGORIES:
        return v
    alias = {
        "people": CAT_PERSON, "name": CAT_PERSON, "human": CAT_PERSON,
        "人物": CAT_PERSON, "人名": CAT_PERSON, "姓名": CAT_PERSON,
        "organization": CAT_ORG, "organisation": CAT_ORG, "company": CAT_ORG,
        "employer": CAT_ORG, "机构": CAT_ORG, "公司": CAT_ORG, "单位": CAT_ORG,
        "place": CAT_LOCATION, "address": CAT_LOCATION, "geo": CAT_LOCATION,
        "city": CAT_LOCATION, "地点": CAT_LOCATION, "地址": CAT_LOCATION,
        "title": CAT_ROLE, "position": CAT_ROLE, "job": CAT_ROLE,
        "职务": CAT_ROLE, "职位": CAT_ROLE, "角色": CAT_ROLE,
        "product": CAT_PROJECT, "codename": CAT_PROJECT,
        "项目": CAT_PROJECT, "产品": CAT_PROJECT,
        "time": CAT_DATE, "datetime": CAT_DATE, "日期": CAT_DATE, "时间": CAT_DATE,
        "email": CAT_CONTACT, "phone": CAT_CONTACT, "url": CAT_CONTACT,
        "handle": CAT_CONTACT, "联系方式": CAT_CONTACT, "电话": CAT_CONTACT,
        "id": CAT_ID, "identifier": CAT_ID, "account": CAT_ID,
        "证件": CAT_ID, "账号": CAT_ID, "身份证": CAT_ID,
    }
    return alias.get(v, CAT_OTHER)


@dataclass(frozen=True)
class Span:
    """One identity-bearing surface found in the text.

    `start`/`end` are offsets into the *originating* text when known (regex
    detectors always know them); LLM detections may set them to -1 and rely on
    literal surface matching instead.
    """

    surface: str
    category: str
    source: str = "regex"          # 'regex:<name>' | 'llm' | 'critic'
    confidence: float = 1.0
    start: int = -1
    end: int = -1
    note: str = ""                  # sub-kind, e.g. 'email', 'cn-mobile'
    aliases: tuple = field(default=())  # other surfaces of the same entity

    def with_category(self, category: str) -> "Span":
        return Span(self.surface, category, self.source, self.confidence,
                    self.start, self.end, self.note, self.aliases)


def merge_overlapping(spans: List[Span]) -> List[Span]:
    """Resolve offset overlaps: keep the longest, breaking ties by confidence.

    Only applies to spans with real offsets; surface-only spans (start < 0) pass
    through untouched and are de-duplicated later by the Vault.
    """
    anchored = sorted(
        (s for s in spans if s.start >= 0 and s.end > s.start),
        key=lambda s: (s.start, -(s.end - s.start), -s.confidence),
    )
    floating = [s for s in spans if not (s.start >= 0 and s.end > s.start)]

    kept: List[Span] = []
    occupied_end = -1
    for s in anchored:
        if s.start >= occupied_end:        # no overlap with the last kept span
            kept.append(s)
            occupied_end = s.end
        # else: fully or partially shadowed by a longer/earlier span -> drop
    return kept + floating
