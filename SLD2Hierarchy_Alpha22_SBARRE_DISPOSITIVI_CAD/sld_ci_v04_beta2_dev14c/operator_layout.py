"""Console Human-in-the-Loop helper for unresolved MV feeder labels.

The helper never invents the source labels. It displays structurally recovered
feeders in their deterministic synthetic order and asks the operator to provide
actual labels. Feedback is saved with OPERATOR_PROVIDED provenance and can be
reused by the plant-scoped knowledge store on later runs.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List

from .operator_interaction import validate_feedback


def _load(path: str) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _ordered_unresolved(analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = list((analysis.get("layout_resolution", {}) or {}).get("unresolved_line_labels", []) or [])
    return sorted(rows, key=lambda r: str(r.get("synthetic_line_key") or ""))


def _cu_membership_by_feeder(analysis: Dict[str, Any]) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = defaultdict(list)
    for m in (analysis.get("layout_resolution", {}) or {}).get("cu_mv_membership", []) or []:
        sk = m.get("synthetic_line_key") or m.get("mv_line_instance_key")
        if sk is not None:
            out[str(sk)].append(str(m.get("cu_instance_key")))
    for key in list(out):
        out[key] = sorted(out[key], key=lambda x: (not x.isdigit(), int(x) if x.isdigit() else x))
    return out


def _request_id(analysis: Dict[str, Any]) -> str:
    for r in analysis.get("layout_resolution_requests", []) or []:
        if r.get("target") == "MV_LINE_LABEL_MAPPING":
            return str(r.get("request_id"))
    plant_id = str((analysis.get("plant", {}) or {}).get("plant_id") or "PLANT")
    return f"{plant_id}::REQ::MV_LINE_LABEL_MAPPING"


def build_feedback(analysis: Dict[str, Any], labels: List[str]) -> Dict[str, Any]:
    rows = _ordered_unresolved(analysis)
    if not rows:
        raise ValueError("No unresolved MV line labels are present in the analysis")
    if len(labels) != len(rows):
        raise ValueError(f"Expected {len(rows)} labels, received {len(labels)}")
    mapping = {
        str(row["synthetic_line_key"]): str(label).strip()
        for row, label in zip(rows, labels)
        if str(label).strip()
    }
    if len(mapping) != len(rows):
        raise ValueError("Every unresolved feeder requires a non-empty operator label")
    plant_id = str((analysis.get("plant", {}) or {}).get("plant_id") or "") or None
    layout_doc = (analysis.get("sources", {}) or {}).get("layout", {}) or {}
    record = {
        "request_id": _request_id(analysis),
        "target": "MV_LINE_LABEL_MAPPING",
        "option": "PROVIDE_VALUE",
        "value": mapping,
        "status": "OPERATOR_PROVIDED",
        "doc": layout_doc.get("doc_id"),
        "plant_id": plant_id,
        "learning_scope": "PLANT",
        "context": {
            "plant_id": plant_id,
            "source_role": "LAYOUT",
            "source_file": layout_doc.get("file_name"),
            "mapping_basis": "OPERATOR_LABELS_FOR_STRUCTURALLY_RECOVERED_FEEDERS",
        },
    }
    return validate_feedback(record)


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="sld-ci-layout-operator",
        description="Resolve structurally recovered MV feeder labels with operator-provided source labels.",
    )
    parser.add_argument("--analysis", required=True, help="dev8 analysis JSON")
    parser.add_argument("--feedback", required=True, help="output feedback JSON")
    parser.add_argument(
        "--labels",
        default=None,
        help="Non-interactive labels separated by | in feeder order, e.g. 'LINEA 1|LINEA 2|LINEA 3'",
    )
    args = parser.parse_args()

    analysis = _load(args.analysis)
    rows = _ordered_unresolved(analysis)
    if not rows:
        print("No unresolved MV feeder labels. Nothing to do.")
        return 0

    memberships = _cu_membership_by_feeder(analysis)
    print("\nUnresolved structural MV feeders:")
    for idx, row in enumerate(rows, 1):
        key = str(row.get("synthetic_line_key"))
        raw = row.get("raw_header_text")
        cus = memberships.get(key, [])
        print(f"  {idx:02d}. {key} | page={row.get('page')} | raw_header={raw!r} | CU={', '.join(cus) if cus else '-'}")

    if args.labels is not None:
        labels = [x.strip() for x in args.labels.split("|")]
    else:
        print("\nEnter the actual source labels in the SAME order, separated by |.")
        print("Example: LINEA 1|LINEA 2|LINEA 3")
        raw = input("Labels: ").strip()
        if not raw:
            print("No feedback saved.")
            return 1
        labels = [x.strip() for x in raw.split("|")]

    record = build_feedback(analysis, labels)
    out = {"operator_feedback": [record]}
    p = Path(args.feedback)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Feedback saved: {p}")
    print("Provenance: OPERATOR_PROVIDED | learning scope: PLANT")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
