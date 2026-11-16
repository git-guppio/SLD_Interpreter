"""Extract conservative MV-line semantic evidence from layout text.

Dev9 recognizes explicit standalone circuit identifiers such as MV-01 / MV_01
in addition to multilingual "line/feeder" phrases.  It emits every identifier
found in a text item; multiple circuit labels are often packed into one PDF text
span on overview drawings.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Tuple

from .ingestion import ascii_fold, norm_text

_STANDALONE_MV = re.compile(r"\bMV\s*[-_]?\s*(\d{1,3})\b", re.I)
_PHRASE_PATTERNS = [
    re.compile(r"\b(?:LINEA|LINE|LIGNE|LINHA)\s*(?:MT|MV)\s*[-:#.]?\s*([A-Z0-9][A-Z0-9._/-]*)\b", re.I),
    re.compile(r"\b(?:MT|MV)\s*(?:LINEA|LINE|LIGNE|LINHA)\s*[-:#.]?\s*([A-Z0-9][A-Z0-9._/-]*)\b", re.I),
    re.compile(r"\bFEEDERS?\b\s*[-:#.]?\s*((?:[A-Z]+)?\d+[A-Z0-9._/-]*|[A-Z])\b", re.I),
    re.compile(r"\b(?:CIRCUITO|CIRCUIT)\s*(?:MT|MV)?\s*[-:#.]?\s*((?:[A-Z]+)?\d+[A-Z0-9._/-]*)\b", re.I),
]
_FAMILY = re.compile(
    r"\b(?:LINEA|LINE|LIGNE|LINHA|FEEDER|CIRCUITO|CIRCUIT)\b.*\b(?:MT|MV)\b|"
    r"\b(?:MT|MV)\b.*\b(?:LINEA|LINE|LIGNE|LINHA)\b",
    re.I,
)


def _canonical_mv_number(raw: str) -> str:
    return f"MV-{int(raw):02d}"


def _explicit_ids(folded: str) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    spans = set()
    for m in _STANDALONE_MV.finditer(folded):
        key = _canonical_mv_number(m.group(1))
        out.append((key, "STANDALONE_MV_IDENTIFIER"))
        spans.add(m.span())
    # Phrase forms remain useful for LINEA MT 1 / FEEDER A where no standalone
    # MV token exists.  They preserve the actual source identifier.
    for rx in _PHRASE_PATTERNS:
        for m in rx.finditer(folded):
            val = str(m.group(1)).strip(" .:-")
            if not val:
                continue
            if val.isdigit() and "MV" in m.group(0).upper():
                key = _canonical_mv_number(val)
            else:
                key = val.upper().replace("_", "-")
            out.append((key, "EXPLICIT_MV_LINE_IDENTIFIER"))
    # stable dedupe per text item
    seen = set()
    ans = []
    for x in out:
        if x[0] in seen:
            continue
        seen.add(x[0])
        ans.append(x)
    return ans


def detect_mv_line_anchors(text_items: Iterable[Any], page_no: int, doc_id: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seq = 0
    for item in text_items:
        raw = norm_text(getattr(item, "text", ""))
        folded = ascii_fold(raw).upper()
        if not folded:
            continue
        # Cable/insulation specifications such as ``35kV TR-XLPE ... MV-105``
        # are not feeder identifiers.  Treat that local semantic context as a
        # hard contradiction for line-instance extraction.
        non_line_mv_context = bool(re.search(r"\b(?:TR-XLPE|KCMIL|AWG|INSULATION|CONDUCTOR\s+SIZE)\b", folded))
        ids = [] if non_line_mv_context else _explicit_ids(folded)
        if ids:
            for line_key, kind in ids:
                seq += 1
                out.append({
                    "anchor_id": f"{doc_id}_P{page_no:03d}_MVLINE_{seq:04d}",
                    "text": raw,
                    "bbox": list(getattr(item, "bbox", (0, 0, 0, 0))),
                    "page": page_no,
                    "doc": doc_id,
                    "equipment_type": "MV_LINE",
                    "anchor_role": "INSTANCE",
                    "evidence_kind": kind,
                    "line_instance_hint": line_key,
                    "confidence": getattr(item, "confidence", None),
                    "source": getattr(item, "source", None),
                })
        elif _FAMILY.search(folded):
            seq += 1
            out.append({
                "anchor_id": f"{doc_id}_P{page_no:03d}_MVLINE_{seq:04d}",
                "text": raw,
                "bbox": list(getattr(item, "bbox", (0, 0, 0, 0))),
                "page": page_no,
                "doc": doc_id,
                "equipment_type": "MV_LINE",
                "anchor_role": "FAMILY",
                "evidence_kind": "MV_LINE_FAMILY_MENTION",
                "line_instance_hint": None,
                "confidence": getattr(item, "confidence", None),
                "source": getattr(item, "source", None),
            })
    return out
