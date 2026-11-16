from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple

Point = Tuple[float, float]
BBox = Tuple[float, float, float, float]


@dataclass
class TextItem:
    text: str
    bbox: BBox
    page: int
    doc: str
    confidence: Optional[float] = 1.0
    source: str = "NATIVE_PDF_TEXT"


@dataclass
class VectorSegment:
    segment_id: int
    orientation: str             # H | V
    p1: Point
    p2: Point
    length_pt: float
    color_name: str
    rgb: Optional[Tuple[float, float, float]]
    stroke_width: Optional[float]
    drawing_index: int
    source_item_index: int
    is_near_black: bool


@dataclass
class GraphNode:
    node_id: int
    point: Point
    node_type: str               # ENDPOINT | STRAIGHT | CORNER | T_JUNCTION | MULTI_JUNCTION
    degree: int
    incident_edge_ids: List[int] = field(default_factory=list)
    evidence: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphEdge:
    edge_id: int
    source: int
    target: int
    p1: Point
    p2: Point
    length_pt: float
    orientation: str
    source_segment_ids: List[int] = field(default_factory=list)
    color_names: List[str] = field(default_factory=list)
    stroke_widths: List[float] = field(default_factory=list)


@dataclass
class CrossingRecord:
    point: Point
    horizontal_segment_ids: List[int]
    vertical_segment_ids: List[int]
    electrical_join: bool = False
    reason: str = "INTERIOR_INTERIOR_CROSSING_NO_SOURCE_JUNCTION_EVIDENCE"


@dataclass
class PageGraphResult:
    page: int
    doc: str
    page_type: str
    page_width_pt: float
    page_height_pt: float
    rotation_degrees: int
    source_segment_count: int
    accepted_segment_count: int
    nodes: List[GraphNode]
    edges: List[GraphEdge]
    crossings: List[CrossingRecord]
    connected_component_count: int
    node_type_counts: Dict[str, int]
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TextEquipmentAnchor:
    anchor_id: str
    equipment_type: str
    text: str
    bbox: BBox
    page: int
    doc: str
    confidence: float
    evidence_kind: str
    source: str
    tag: Optional[str] = None
    attributes: Dict[str, Any] = field(default_factory=dict)
    anchor_role: str = "INSTANCE"


@dataclass
class TerminalBinding:
    terminal_id: str
    graph_node_id: int
    point: Point
    side: str
    distance_to_symbol_border_pt: float
    confidence: float
    evidence: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SymbolCandidate:
    symbol_id: str
    candidate_type: str
    bbox: BBox
    center: Point
    page: int
    doc: str
    confidence: float
    evidence_state: str          # GEOMETRY_ONLY | TEXT_ONLY | FUSED
    geometry_kind: Optional[str] = None
    text_anchor_id: Optional[str] = None
    tag: Optional[str] = None
    terminals: List[TerminalBinding] = field(default_factory=list)
    evidence: Dict[str, Any] = field(default_factory=dict)
    accepted_entity: bool = False


@dataclass
class TracedRelationCandidate:
    relation_id: str
    source_symbol_id: str
    target_symbol_id: str
    relation_type: str              # CONNECTS_TO_CANDIDATE
    direction_status: str           # UNRESOLVED
    page: int
    doc: str
    confidence: float
    source_terminal_id: str
    target_terminal_id: str
    path_length_pt: float
    path_node_ids: List[int] = field(default_factory=list)
    path_edge_ids: List[int] = field(default_factory=list)
    branch_node_count: int = 0
    accepted_relation: bool = False
    evidence: Dict[str, Any] = field(default_factory=dict)
