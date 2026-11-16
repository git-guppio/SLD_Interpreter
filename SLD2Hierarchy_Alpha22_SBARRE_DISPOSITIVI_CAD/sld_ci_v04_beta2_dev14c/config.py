from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GeometryThresholds:
    """
    Central-Inverter v0.4-alpha1 geometry.

    Values preserve the stable dev29 scale where applicable. The alpha1
    experiment changes representation, not the calibrated extraction thresholds.
    """
    vector_border_margin_ratio: float = 0.01
    vector_border_margin_min_pt: float = 8.0
    vector_min_segment_length_pt: float = 8.0
    vector_orthogonality_tolerance: float = 0.02

    vector_snap_tol_ratio: float = 0.0015
    vector_snap_tol_min_pt: float = 1.0

    # Near-black definition retained from dev29.
    near_black_max_channel: float = 0.08

    # Hard safety caps only.
    max_near_black_line_items: int = 60000
    max_candidate_segments: int = 20000

    # Graph building
    intersection_tolerance_multiplier: float = 1.0

    # A thick conductor can later become BUS evidence. Alpha1 reports it but
    # does not yet promote an asset or hierarchy node.
    bus_width_ratio_to_median: float = 2.5
    bus_min_taps: int = 3

    # Symbol candidate generation (alpha2)
    symbol_min_bbox_pt: float = 1.5
    symbol_max_bbox_ratio: float = 0.12
    symbol_rect_aspect_min: float = 0.20
    symbol_rect_aspect_max: float = 5.0
    symbol_terminal_search_radius_min_pt: float = 5.0
    symbol_terminal_search_radius_ratio: float = 0.003
    symbol_text_fusion_distance_min_pt: float = 35.0
    symbol_text_fusion_distance_ratio: float = 0.025
    symbol_max_terminal_count: int = 12
    symbol_candidate_cap: int = 5000

    # Terminal-to-terminal tracing (alpha3)
    trace_max_path_length_ratio: float = 1.50
    trace_max_path_length_min_pt: float = 600.0
    trace_symbol_interior_margin_pt: float = 0.75
    trace_max_relations_per_symbol: int = 12

    # Central-Inverter symbol scale coherence (alpha4)
    ci_scale_seed_search_radius_min_pt: float = 45.0
    ci_scale_seed_search_radius_ratio: float = 0.025
    ci_scale_seed_min_side_pt: float = 6.0
    ci_scale_seed_max_side_pt: float = 120.0

    # Same equipment family is expected to use the same symbol scale.
    # Rotation is normalized by comparing short/long sides.
    ci_scale_consistent_ratio_min: float = 0.65
    ci_scale_consistent_ratio_max: float = 1.55


@dataclass
class RunConfig:
    dpi: int = 150
    lang: str = "eng+spa"
    ocr_mode: str = "never"      # never | auto | always
    include_colored_inventory: bool = False
    max_pages: int | None = None
    geometry: GeometryThresholds = GeometryThresholds()
