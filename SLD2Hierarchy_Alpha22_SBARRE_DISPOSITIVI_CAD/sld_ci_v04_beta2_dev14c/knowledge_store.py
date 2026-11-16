"""Local JSON knowledge store for reusable operator-taught patterns.

Knowledge is advisory. Direct SLD evidence always has precedence.
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

SCHEMA_VERSION = 2


class KnowledgeStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.data: Dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "patterns": [],
            "operator_feedback": [],
        }
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            return
        obj = json.loads(self.path.read_text(encoding="utf-8"))
        ver = obj.get("schema_version", 1)
        if ver not in {1, SCHEMA_VERSION}:
            raise ValueError("Unsupported knowledge-store schema version")
        if ver == 1:
            obj["schema_version"] = SCHEMA_VERSION
            for p in obj.get("patterns", []):
                p.setdefault("enabled", True)
                p.setdefault("pattern_format", "REGEX")
                p.setdefault("scope", "GENERAL")
        self.data = obj

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")

    def add_feedback(self, record: Dict[str, Any]) -> None:
        self.data.setdefault("operator_feedback", []).append(dict(record))

    def add_pattern(self, pattern: Dict[str, Any]) -> str:
        canonical = dict(pattern)
        canonical.setdefault("origin", "OPERATOR_PROVIDED")
        canonical.setdefault("scope", "GENERAL")
        canonical.setdefault("enabled", True)
        canonical.setdefault("pattern_format", "REGEX")
        canonical.setdefault("support_count", 1)
        canonical.setdefault("usage_count", 0)
        canonical.setdefault("success_count", 0)
        canonical.setdefault("conflict_count", 0)
        existing = self.find_equivalent(canonical)
        if existing:
            existing["support_count"] = int(existing.get("support_count", 1)) + 1
            return existing["pattern_id"]
        canonical.setdefault("pattern_id", f"LP_{len(self.data.setdefault('patterns', [])) + 1:05d}")
        self.data["patterns"].append(canonical)
        return canonical["pattern_id"]

    def find_equivalent(self, pattern: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        keys = ("pattern_type", "entity_type", "pattern", "scope")
        for item in self.data.get("patterns", []):
            if all(item.get(k) == pattern.get(k) for k in keys):
                return item
        return None

    def patterns(self, pattern_type: Optional[str] = None) -> List[Dict[str, Any]]:
        vals = [p for p in self.data.get("patterns", []) if p.get("enabled", True)]
        if pattern_type is not None:
            vals = [p for p in vals if p.get("pattern_type") == pattern_type]
        return vals
