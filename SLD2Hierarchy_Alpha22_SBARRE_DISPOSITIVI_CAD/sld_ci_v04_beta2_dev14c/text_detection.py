from __future__ import annotations

import re
from typing import Any, List, Optional

from .models import TextEquipmentAnchor, TextItem


CU_PATTERNS = [
    (
        "CU_UNIDAD_CONVERSION",
        re.compile(
            r"\bUNIDAD\s+DE\s+CONVERSI[ÓO]N\s*[-:#]?\s*(\d+)?\b",
            re.I,
        ),
        0.98,
    ),
    (
        "CU_CONVERSION_UNIT",
        re.compile(
            r"\b(?:POWER\s+)?CONVERSION\s+UNIT\s*[-:#]?\s*(\d+)?\b",
            re.I,
        ),
        0.97,
    ),
    (
        "CU_POWER_CONVERTER_UNIT",
        re.compile(
            r"\bPOWER\s+CONVERTER\s+UNIT\s*[-:#]?\s*(\d+)?\b",
            re.I,
        ),
        0.97,
    ),
    (
        "CU_CENTRO_TRANSFORMACION",
        re.compile(
            r"\bCENTRO\s+DE\s+TRANSFORMA(?:CI[ÓO]N|ÇÃO)\s*"
            r"(?:CT)?\s*[-:#]?\s*(\d+)?\b",
            re.I,
        ),
        0.97,
    ),
    (
        "CU_ELECTROCENTRO",
        re.compile(
            r"\b(?:ELETRO|ELECTRO)CENTRO\s*[-:#]?\s*(\d+)?\b",
            re.I,
        ),
        0.95,
    ),
    (
        "CU_CABIN",
        re.compile(
            r"\bCABIN(?:A|E)?\s*[-:#]?\s*(\d+)\b",
            re.I,
        ),
        0.94,
    ),
    (
        "CU_SUBCAMPO",
        re.compile(
            r"\bSUBCAMPO\s*[-:#]?\s*(\d+)\b",
            re.I,
        ),
        0.88,
    ),
]


CU_SHORT_RE = re.compile(
    r"\bCU\s*[-:#]?\s*(\d+)\b",
    re.I,
)

TPO_RE = re.compile(
    r"\b([A-Z0-9]+)-TPO-(\d{2})-(\d{2})\b",
    re.I,
)

XFR_RE = re.compile(
    r"\bXFR[-_ ]?(\d{1,3})\b",
    re.I,
)

INV_HYPHEN_RE = re.compile(
    r"\b([A-Z0-9]+)-INV-(\d{2})-(\d{2})\b",
    re.I,
)

INV_DOT_RE = re.compile(
    r"\bINV[.]?(\d{1,3})[.](\d{1,2})\b",
    re.I,
)

INV_FAMILY_RE = re.compile(
    r"\bINVERTER\s+(\d+)\s*/\s*(\d+)\b",
    re.I,
)

INVERSOR_FAMILY_RE = re.compile(
    r"\bINVERSOR\s+(\d+)\s*/\s*(\d+)\b",
    re.I,
)

CST_RE = re.compile(
    r"\b([A-Z0-9]+)-CST-(\d{2})-I(\d{2})-[A-Z0-9-]+\b",
    re.I,
)

LVL_SB_RE = re.compile(
    r"\bLVL-SB[.](\d{1,3})[.](\d{1,2})[.](\d{1,2})"
    r"-INV[.]\d{1,3}[.]\d{1,2}\b",
    re.I,
)

CBX_RE = re.compile(
    r"\bCBX[-_ ]?(\d{1,3})(?:[.]\d+)?\b",
    re.I,
)

QPS_RE = re.compile(
    r"\bQPS[-_](\d+)[-_](\d+)[/](\d+)\b",
    re.I,
)


# ------------------------------------------------------------------
# Generic multilingual semantic mentions
# ------------------------------------------------------------------

TRANSFORMER_MENTION_RE = re.compile(
    r"\b(?:"
    r"TRANSFORMADOR(?:ES)?|"
    r"TRANSFORMER(?:S)?|"
    r"TRAFO(?:S)?"
    r")\b",
    re.I,
)

INVERTER_MENTION_RE = re.compile(
    r"\b(?:"
    r"INVERTER(?:S)?|"
    r"INVERSOR(?:ES)?|"
    r"POWER\s+CONVERTER(?:S)?"
    r")\b",
    re.I,
)


APPARENT_POWER_RATING_RE = re.compile(
    r"\b(\d+(?:[.,]\d+)?)\s*(KVA|MVA)\b",
    re.I,
)

# Voltage-ratio evidence. Supports common SLD notations such as
# ``0,36/33KV`` and ``33KV/360V/360V``.  A missing unit on one side
# inherits the nearest explicit unit; this is representation parsing only,
# not equipment classification.
VOLTAGE_RATIO_RE = re.compile(
    r"\b(\d+(?:[.,]\d+)?)\s*(KV|V)?\s*/\s*"
    r"(\d+(?:[.,]\d+)?)\s*(KV|V)"
    r"(?:\s*/\s*(\d+(?:[.,]\d+)?)\s*(KV|V)?)?\b",
    re.I,
)

CU_REFERENCE_PREFIX_RE = re.compile(
    r"^\s*(?:A|DE|TO|FROM)\s+SUBCAMPO\b",
    re.I,
)

STRING_BOX_MENTION_RE = re.compile(
    r"\b(?:"
    r"STRING\s+BOX(?:ES)?|"
    r"COMBINER\s+BOX(?:ES)?"
    r")\b",
    re.I,
)


def _anchor(
    idx: int,
    equipment_type: str,
    item: TextItem,
    confidence: float,
    evidence_kind: str,
    tag: Optional[str],
    anchor_role: Optional[str] = None,
    **attrs: Any,
) -> TextEquipmentAnchor:

    if anchor_role is None:
        anchor_role = (
            "CARDINALITY"
            if "CARDINALITY" in evidence_kind
            else "TAG"
            if "TAG" in evidence_kind
            else "INSTANCE"
        )

    return TextEquipmentAnchor(
        anchor_id=f"{item.doc}_P{item.page:03d}_TXT_{idx:04d}",
        equipment_type=equipment_type,
        text=item.text,
        bbox=item.bbox,
        page=item.page,
        doc=item.doc,
        confidence=confidence,
        evidence_kind=evidence_kind,
        source=item.source,
        tag=tag,
        anchor_role=anchor_role,
        attributes=attrs,
    )


def detect_text_equipment_anchors(
    items: List[TextItem],
) -> List[TextEquipmentAnchor]:

    """
    Generalized semantic detector.

    Text anchors are evidence only.
    They are not automatically accepted equipment entities.
    """

    out: List[TextEquipmentAnchor] = []
    idx = 0

    for item in items:
        text = item.text

        # ----------------------------------------------------------
        # Generic multilingual family mentions
        # ----------------------------------------------------------
        #
        # FAMILY anchors indicate equipment-family evidence only.
        # They do not identify a unique equipment instance.
        #

        for family_re, equipment_type, evidence_kind, conf in (
            (
                TRANSFORMER_MENTION_RE,
                "TRANSFORMER_CANDIDATE",
                "GENERIC_TRANSFORMER_MENTION",
                0.78,
            ),
            (
                INVERTER_MENTION_RE,
                "CENTRAL_INVERTER",
                "GENERIC_INVERTER_MENTION",
                0.78,
            ),
            (
                STRING_BOX_MENTION_RE,
                "STRING_BOX",
                "GENERIC_STRING_BOX_MENTION",
                0.74,
            ),
        ):
            for m in family_re.finditer(text):
                idx += 1

                out.append(
                    _anchor(
                        idx,
                        equipment_type,
                        item,
                        conf,
                        evidence_kind,
                        None,
                        anchor_role="FAMILY",
                        family_text=m.group(0),
                    )
                )


        # ----------------------------------------------------------
        # Apparent-power rating evidence
        # ----------------------------------------------------------
        # A kVA/MVA value is strong semantic evidence for a power
        # conversion device, but is NOT sufficient by itself to classify
        # a transformer.  Keep it as a TRANSFORMER_CANDIDATE rating anchor
        # for downstream resolution / human-in-the-loop guidance.
        for m in APPARENT_POWER_RATING_RE.finditer(text):
            idx += 1
            raw_value = m.group(1).replace(",", ".")
            try:
                value = float(raw_value)
            except ValueError:
                value = None
            unit = m.group(2).upper()
            kva = value * 1000.0 if value is not None and unit == "MVA" else value
            out.append(
                _anchor(
                    idx,
                    "TRANSFORMER_CANDIDATE",
                    item,
                    0.88,
                    "APPARENT_POWER_RATING",
                    None,
                    anchor_role="RATING",
                    apparent_power_value=value,
                    apparent_power_unit=unit,
                    apparent_power_kva=kva,
                )
            )

        # ----------------------------------------------------------
        # Voltage-ratio evidence
        # ----------------------------------------------------------
        for m in VOLTAGE_RATIO_RE.finditer(text):
            idx += 1

            raw_values = [m.group(1), m.group(3), m.group(5)]
            raw_units = [m.group(2), m.group(4), m.group(6)]
            explicit_units = [u.upper() if u else None for u in raw_units]

            # In notations such as 0,36/33KV the first value inherits KV.
            inherited = next((u for u in explicit_units if u), None)
            units = [u or inherited for u in explicit_units]
            values_v = []
            values_raw = []
            for raw_v, unit in zip(raw_values, units):
                if raw_v is None:
                    continue
                try:
                    value = float(raw_v.replace(",", "."))
                except ValueError:
                    continue
                values_raw.append(value)
                if unit == "KV":
                    values_v.append(value * 1000.0)
                elif unit == "V":
                    values_v.append(value)

            out.append(
                _anchor(
                    idx,
                    "TRANSFORMER_CANDIDATE",
                    item,
                    0.93,
                    "VOLTAGE_RATIO",
                    None,
                    anchor_role="CHARACTERISTIC",
                    voltage_values_raw=values_raw,
                    voltage_values_v=values_v,
                    voltage_units=units[:len(values_raw)],
                )
            )

        # ----------------------------------------------------------
        # Conversion Units
        # ----------------------------------------------------------

        for kind, pat, conf in CU_PATTERNS:
            for m in pat.finditer(text):
                idx += 1

                raw = m.group(1) if m.lastindex else None
                role = "INSTANCE"
                representation_role = "SOURCE_INSTANCE"
                if kind == "CU_SUBCAMPO" and CU_REFERENCE_PREFIX_RE.search(text):
                    role = "REFERENCE"
                    representation_role = "CROSS_SHEET_REFERENCE"

                out.append(
                    _anchor(
                        idx,
                        "CONVERSION_UNIT",
                        item,
                        conf,
                        kind,
                        m.group(0),
                        anchor_role=role,
                        instance_hint=(
                            int(raw)
                            if raw and raw.isdigit()
                            else None
                        ),
                        representation_role=representation_role,
                    )
                )

        m = CU_SHORT_RE.search(text)

        if m:
            idx += 1

            out.append(
                _anchor(
                    idx,
                    "CONVERSION_UNIT",
                    item,
                    0.83,
                    "CU_SHORT_LABEL",
                    m.group(0),
                    instance_hint=int(m.group(1)),
                )
            )

        # ----------------------------------------------------------
        # Transformers
        # ----------------------------------------------------------

        for m in TPO_RE.finditer(text):
            idx += 1

            out.append(
                _anchor(
                    idx,
                    "MV_LV_TRANSFORMER",
                    item,
                    0.99,
                    "TPO_TAG",
                    m.group(0),
                    cu_instance_hint=int(m.group(2)),
                    transformer_instance_hint=int(m.group(3)),
                )
            )

        for m in XFR_RE.finditer(text):
            idx += 1

            out.append(
                _anchor(
                    idx,
                    "TRANSFORMER_CANDIDATE",
                    item,
                    0.93,
                    "XFR_TAG",
                    m.group(0),
                    xfr_instance_hint=int(m.group(1)),
                )
            )

        # ----------------------------------------------------------
        # Inverters
        # ----------------------------------------------------------

        for m in INV_HYPHEN_RE.finditer(text):
            idx += 1

            out.append(
                _anchor(
                    idx,
                    "CENTRAL_INVERTER",
                    item,
                    0.99,
                    "INV_HYPHEN_TAG",
                    m.group(0),
                    cu_instance_hint=int(m.group(2)),
                    inverter_instance_hint=int(m.group(3)),
                )
            )

        for m in INV_DOT_RE.finditer(text):
            idx += 1

            out.append(
                _anchor(
                    idx,
                    "CENTRAL_INVERTER",
                    item,
                    0.98,
                    "INV_DOT_TAG",
                    m.group(0),
                    cu_instance_hint=int(m.group(1)),
                    inverter_instance_hint=int(m.group(2)),
                )
            )

        # Cardinality declarations such as:
        # INVERTER 1/3
        # INVERSOR 2/4
        #
        # These must NOT be treated as equipment instances.

        for family_re, kind in (
            (
                INV_FAMILY_RE,
                "INVERTER_FAMILY_CARDINALITY",
            ),
            (
                INVERSOR_FAMILY_RE,
                "INVERSOR_FAMILY_CARDINALITY",
            ),
        ):
            for m in family_re.finditer(text):
                idx += 1

                out.append(
                    _anchor(
                        idx,
                        "CENTRAL_INVERTER",
                        item,
                        0.96,
                        kind,
                        m.group(0),
                        anchor_role="CARDINALITY",
                        member_index=int(m.group(1)),
                        declared_member_count=int(m.group(2)),
                    )
                )

        # ----------------------------------------------------------
        # String Boxes
        # ----------------------------------------------------------

        for m in CST_RE.finditer(text):
            idx += 1

            out.append(
                _anchor(
                    idx,
                    "STRING_BOX",
                    item,
                    0.99,
                    "CST_TAG",
                    m.group(0),
                    cu_instance_hint=int(m.group(2)),
                    inverter_instance_hint=int(m.group(3)),
                )
            )

        for m in LVL_SB_RE.finditer(text):
            idx += 1

            out.append(
                _anchor(
                    idx,
                    "STRING_BOX",
                    item,
                    0.99,
                    "LVL_SB_TAG",
                    m.group(0),
                    cu_instance_hint=int(m.group(1)),
                    inverter_instance_hint=int(m.group(2)),
                    string_box_instance_hint=int(m.group(3)),
                )
            )

        for m in CBX_RE.finditer(text):
            idx += 1

            out.append(
                _anchor(
                    idx,
                    "STRING_BOX",
                    item,
                    0.96,
                    "CBX_TAG",
                    m.group(0),
                    string_box_instance_hint=int(m.group(1)),
                )
            )

        # ----------------------------------------------------------
        # DC distribution candidate
        # ----------------------------------------------------------
        #
        # QPS is intentionally NOT promoted to STRING_BOX.
        #

        for m in QPS_RE.finditer(text):
            idx += 1

            out.append(
                _anchor(
                    idx,
                    "DC_DISTRIBUTION_CANDIDATE",
                    item,
                    0.90,
                    "QPS_TAG",
                    m.group(0),
                    family_index=int(m.group(1)),
                    member_index=int(m.group(2)),
                    declared_member_count=int(m.group(3)),
                )
            )

    # --------------------------------------------------------------
    # Deterministic dedupe
    # --------------------------------------------------------------

    seen = set()
    deduped: List[TextEquipmentAnchor] = []

    for a in out:
        key = (
            a.doc,
            a.page,
            a.equipment_type,
            (a.tag or "").upper(),
            tuple(round(v, 1) for v in a.bbox),
            a.evidence_kind,
            a.anchor_role,
        )

        if key in seen:
            continue

        seen.add(key)
        deduped.append(a)

    return deduped