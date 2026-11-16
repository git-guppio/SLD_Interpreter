"""Document-level semantic cues kept separate from equipment instances."""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List


def _norm(s: Any) -> str:
    return " ".join(str(s or "").strip().upper().split())


TYPICAL_SKID_RE = re.compile(r"\b(?:INVERTER\s*)?\(?TYPICAL\s+FOR\s+(\d{1,5})\s+SKIDS?\)?", re.I)
POWER_BLOCK_RE = re.compile(r"\bPOWER\s+BLOCK\b", re.I)
SKID_RE = re.compile(r"\bSKIDS?\b", re.I)
INTERMEDIATE_STEP_UP_RE = re.compile(r"\bINTERMEDIATE\s+STEP\s+UP\s+TRANSFORMER\b", re.I)
FROM_INVERTER_RE = re.compile(r"\bFROM\s+INVERTER\b", re.I)
COMBINER_RE = re.compile(r"\bCOMBINER\s+BOX(?:ES)?\b", re.I)
PROJECT_SUBSTATION_RE = re.compile(r"\bPROJECT\s+SUBSTATION\b", re.I)
SUBSTATION_BREAKER_RE = re.compile(r"\bSUBSTATION\s+BREAKER\b", re.I)
MV_BUSBAR_RE = re.compile(r"\b(?:MV|MEDIUM\s+VOLTAGE)\s+BUS(?:BAR)?\b|\bBUS(?:BAR)?\s+(?:MV|MEDIUM\s+VOLTAGE)\b", re.I)
HV_MV_RE = re.compile(r"\b(?:HV\s*/\s*MV|HIGH\s+VOLTAGE.*MEDIUM\s+VOLTAGE|MAIN\s+POWER\s+TRANSFORMER)\b", re.I)


def extract_document_semantics(items: Iterable[Any]) -> Dict[str, Any]:
    texts = [_norm(getattr(x, "text", "")) for x in items if _norm(getattr(x, "text", ""))]
    joined = " \n ".join(texts)
    skid_counts: List[int] = []
    skid_evidence: List[Dict[str, Any]] = []
    for item in items:
        t = _norm(getattr(item, "text", ""))
        for m in TYPICAL_SKID_RE.finditer(t):
            count = int(m.group(1))
            skid_counts.append(count)
            skid_evidence.append({
                "count": count,
                "text": str(getattr(item, "text", "")),
                "page": getattr(item, "page", None),
                "doc": getattr(item, "doc", None),
                "bbox": list(getattr(item, "bbox", (0, 0, 0, 0))),
                "source": getattr(item, "source", None),
            })
    return {
        "has_power_block_family": bool(POWER_BLOCK_RE.search(joined)),
        "has_skid_family": bool(SKID_RE.search(joined)),
        "has_intermediate_step_up_transformer": bool(INTERMEDIATE_STEP_UP_RE.search(joined)),
        "has_from_inverter": bool(FROM_INVERTER_RE.search(joined)),
        "has_combiner_box_family": bool(COMBINER_RE.search(joined)),
        "has_project_substation": bool(PROJECT_SUBSTATION_RE.search(joined)),
        "has_substation_breaker": bool(SUBSTATION_BREAKER_RE.search(joined)),
        "has_mv_busbar": bool(MV_BUSBAR_RE.search(joined)),
        "has_hv_mv_transformer_context": bool(HV_MV_RE.search(joined)),
        "typical_skid_counts": sorted(set(skid_counts)),
        "typical_skid_evidence": skid_evidence,
    }
