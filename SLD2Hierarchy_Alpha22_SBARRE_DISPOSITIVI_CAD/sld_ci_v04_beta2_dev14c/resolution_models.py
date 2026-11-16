"""Typed records for human-in-the-loop resolution requests and feedback."""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


@dataclass
class ResolutionRequest:
    request_id: str
    target: str
    reason: str
    doc: str
    page: Optional[int] = None
    group_ids: List[str] = field(default_factory=list)
    candidate_values: List[str] = field(default_factory=list)
    interaction_mode: str = "PROVIDE_VALUE"  # or CONFIRM_CANDIDATE / VISUAL_SELECT
    required_for: str = "MINIMUM_TARGET_HIERARCHY"
    status: str = "OPEN"
    context: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class OperatorFeedback:
    request_id: str
    feedback_type: str
    value: Any = None
    bbox: Optional[List[float]] = None
    page: Optional[int] = None
    device_type: Optional[str] = None
    status: str = "OPERATOR_PROVIDED"
    context: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
