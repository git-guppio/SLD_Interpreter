from __future__ import annotations

import math
import re
import unicodedata
from collections import defaultdict
from typing import Any, Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np
import pymupdf as fitz
import pytesseract

from .config import GeometryThresholds
from .models import TextItem, VectorSegment


def norm_text(text: str) -> str:
    return " ".join((text or "").replace("\u00a0", " ").split())


def ascii_fold(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", text or "")
        if not unicodedata.combining(c)
    )


def _bbox_union(boxes: Sequence[Sequence[float]]) -> Tuple[float, float, float, float]:
    return (
        min(float(b[0]) for b in boxes),
        min(float(b[1]) for b in boxes),
        max(float(b[2]) for b in boxes),
        max(float(b[3]) for b in boxes),
    )


def native_text_items(
    page: fitz.Page,
    page_no: int,
    doc_id: str,
) -> Tuple[List[TextItem], Dict[str, Any]]:
    """Stable line-level native extraction adapted from dev29."""
    items: List[TextItem] = []
    raw = page.get_text("dict")
    char_count = 0
    alpha_count = 0

    for block in raw.get("blocks", []):
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            text = norm_text(" ".join(s.get("text", "") for s in spans))
            if not text:
                continue
            boxes = [s["bbox"] for s in spans if "bbox" in s]
            if not boxes:
                continue
            bb = _bbox_union(boxes)
            char_count += len(text)
            alpha_count += sum(ch.isalpha() for ch in text)
            items.append(
                TextItem(
                    text=text,
                    bbox=tuple(round(v, 3) for v in bb),
                    page=page_no,
                    doc=doc_id,
                    confidence=1.0,
                    source="NATIVE_PDF_TEXT",
                )
            )

    return items, {
        "native_text_present": bool(items),
        "native_text_usable": alpha_count >= 60 or char_count >= 180,
        "native_line_count": len(items),
        "native_char_count": char_count,
        "native_alpha_count": alpha_count,
    }


def _render_page(page: fitz.Page, dpi: int) -> np.ndarray:
    zoom = float(dpi) / 72.0
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
        pix.height, pix.width, pix.n
    )
    if pix.n == 4:
        arr = cv2.cvtColor(arr, cv2.COLOR_RGBA2RGB)
    return arr


def _preprocess_ocr(img: np.ndarray) -> np.ndarray:
    if len(img.shape) == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    else:
        gray = img
    clahe = cv2.createCLAHE(clipLimit=1.6, tileGridSize=(8, 8))
    return clahe.apply(gray)


def _render_bbox_px_to_pdf_unrotated(
    page: fitz.Page,
    bbox_px: Sequence[float],
    dpi: int,
) -> Tuple[float, float, float, float]:
    """
    Rotation-safe mapping retained from dev29 tiled OCR:
    rendered/display coordinates -> unrotated PDF coordinates.
    """
    scale = 72.0 / float(dpi)
    pts = []
    x0, y0, x1, y1 = [float(v) for v in bbox_px]
    for x, y in ((x0, y0), (x1, y0), (x0, y1), (x1, y1)):
        rp = fitz.Point(x * scale, y * scale)
        up = rp * page.derotation_matrix
        pts.append((float(up.x), float(up.y)))
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return (
        round(min(xs), 3),
        round(min(ys), 3),
        round(max(xs), 3),
        round(max(ys), 3),
    )


def ocr_text_items_tiled(
    page: fitz.Page,
    page_no: int,
    doc_id: str,
    dpi: int,
    lang: str,
    psm: int = 11,
    max_tile_px: int = 2200,
    overlap_ratio: float = 0.08,
) -> Tuple[List[TextItem], Dict[str, Any]]:
    """Rotation-safe tiled OCR adapted from dev29."""
    import time
    t0 = time.perf_counter()
    img = _render_page(page, dpi=dpi)
    h, w = img.shape[:2]

    n_cols = max(1, int(math.ceil(w / float(max_tile_px))))
    n_rows = max(1, int(math.ceil(h / float(max_tile_px))))
    base_w = w / n_cols
    base_h = h / n_rows
    overlap_x = int(round(base_w * overlap_ratio))
    overlap_y = int(round(base_h * overlap_ratio))

    raw_items: List[TextItem] = []
    errors = 0

    for row in range(n_rows):
        for col in range(n_cols):
            core_x0 = int(round(col * base_w))
            core_x1 = int(round((col + 1) * base_w))
            core_y0 = int(round(row * base_h))
            core_y1 = int(round((row + 1) * base_h))

            x0 = max(0, core_x0 - overlap_x)
            x1 = min(w, core_x1 + overlap_x)
            y0 = max(0, core_y0 - overlap_y)
            y1 = min(h, core_y1 + overlap_y)

            gray = _preprocess_ocr(img[y0:y1, x0:x1])
            try:
                df = pytesseract.image_to_data(
                    gray,
                    lang=lang,
                    config=f"--psm {psm}",
                    output_type=pytesseract.Output.DATAFRAME,
                )
            except Exception:
                errors += 1
                continue

            df = df.dropna(subset=["text"]).copy()
            df["text"] = df["text"].astype(str).str.strip()
            df = df[(df["text"] != "") & (df["conf"] >= 15)].copy()

            if df.empty:
                continue

            for _, rows in df.groupby(
                ["block_num", "par_num", "line_num"], sort=False
            ):
                rows = rows.sort_values("left")
                text = norm_text(" ".join(rows["text"].tolist()))
                if not text:
                    continue

                bb_px = (
                    float(rows["left"].min()) + x0,
                    float(rows["top"].min()) + y0,
                    float((rows["left"] + rows["width"]).max()) + x0,
                    float((rows["top"] + rows["height"]).max()) + y0,
                )
                confs = [
                    float(v) for v in rows["conf"].tolist()
                    if float(v) >= 0
                ]

                raw_items.append(
                    TextItem(
                        text=text,
                        bbox=_render_bbox_px_to_pdf_unrotated(
                            page, bb_px, dpi
                        ),
                        page=page_no,
                        doc=doc_id,
                        confidence=(
                            round((sum(confs) / len(confs)) / 100.0, 4)
                            if confs else None
                        ),
                        source="OCR_TILED",
                    )
                )

    # Overlap dedupe.
    seen = set()
    items: List[TextItem] = []
    for item in raw_items:
        x0, y0, x1, y1 = item.bbox
        cx = (x0 + x1) / 2.0
        cy = (y0 + y1) / 2.0
        key = (
            ascii_fold(item.text).upper(),
            round(cx / 8.0),
            round(cy / 8.0),
        )
        if key in seen:
            continue
        seen.add(key)
        items.append(item)

    return items, {
        "ocr_method": "TILED_SPARSE_NATIVE",
        "ocr_line_count": len(items),
        "ocr_line_count_before_overlap_dedupe": len(raw_items),
        "ocr_dpi": dpi,
        "tile_rows": n_rows,
        "tile_cols": n_cols,
        "tile_count": n_rows * n_cols,
        "page_rotation_degrees": int(page.rotation),
        "errors": errors,
        "processing_seconds": round(time.perf_counter() - t0, 4),
    }


def classify_page_lightweight(text_items: List[TextItem]) -> Tuple[str, List[str]]:
    """
    Classification is metadata only in alpha1.
    IMPORTANT: planar graph construction is NOT gated by this result.
    """
    text = ascii_fold(" ".join(x.text for x in text_items)).upper()
    reasons = []

    # Functional sheet titles outrank incidental tables.  A genuine single-line
    # sheet often embeds conductor/source schedules; the presence of those
    # tables must not demote the page to SCHEDULE.
    if any(k in text for k in (
        "UNIFILAR", "SINGLE LINE", "ESQUEMA UNIFILAR",
        "DIAGRAMA UNIFILAR", "SCHEMA UNIFILARE"
    )):
        return "SLD", ["single-line functional title"]

    if "MV & FO PLAN" in text or "MV AND FO PLAN" in text:
        return "MV_NETWORK_LAYOUT", ["mv-network layout title"]

    if any(k in text for k in ("CIRCUIT SCHEDULE", "BLOCK SCHEDULE", "CABLE SCHEDULE")):
        return "SCHEDULE", ["schedule keyword without overriding single-line title"]

    if any(k in text for k in ("TRENCH PLAN", "ARRAY PLAN", "LAYOUT PLAN")):
        return "LAYOUT_PLAN", ["layout keyword"]

    return "OTHER", reasons


def _color_name(color: Any) -> Tuple[str, Optional[Tuple[float, float, float]]]:
    if color is None:
        return "NONE", None
    try:
        rgb = tuple(round(float(v), 3) for v in color[:3])
    except Exception:
        return "OTHER", None
    known = {
        (0.0, 0.0, 0.0): "BLACK",
        (1.0, 0.0, 0.0): "RED",
        (0.0, 1.0, 0.0): "GREEN",
        (0.0, 1.0, 1.0): "CYAN",
        (0.0, 0.0, 1.0): "BLUE",
        (1.0, 0.0, 1.0): "MAGENTA",
        (1.0, 1.0, 0.0): "YELLOW",
    }
    return known.get(
        rgb, f"RGB_{rgb[0]:.3f}_{rgb[1]:.3f}_{rgb[2]:.3f}"
    ), rgb


def extract_orthogonal_vector_inventory(
    page: fitz.Page,
    geom: GeometryThresholds,
) -> Dict[str, Any]:
    """
    Full drawing scan, with dev29's important cap rule:
    caps apply only AFTER relevance filtering, never to all drawing items.

    Alpha1 returns:
      - accepted_segments: near-black orthogonal conductors for the primary graph
      - colored_inventory: source-only inventory, not accepted connectivity
      - colour profile
    """
    import time
    t0 = time.perf_counter()

    mb = page.mediabox
    page_w = float(mb.width)
    page_h = float(mb.height)
    border_margin = max(
        geom.vector_border_margin_min_pt,
        min(page_w, page_h) * geom.vector_border_margin_ratio,
    )

    drawings = page.get_drawings()
    accepted: List[VectorSegment] = []
    colored_inventory: Dict[str, List[VectorSegment]] = defaultdict(list)
    profile: Dict[str, Dict[str, float]] = defaultdict(
        lambda: {
            "count": 0,
            "total_length_pt": 0.0,
            "horizontal": 0,
            "vertical": 0,
        }
    )

    total_line_items = 0
    relevant_black_items = 0
    truncated = False
    next_id = 0

    for drawing_idx, d in enumerate(drawings):
        cname, rgb = _color_name(d.get("color"))
        near_black = (
            rgb is not None and max(rgb) <= geom.near_black_max_channel
        )
        stroke_width = d.get("width")
        stroke_width = (
            float(stroke_width) if stroke_width is not None else None
        )

        for item_idx, item in enumerate(d.get("items", [])):
            if not item or item[0] != "l":
                continue

            total_line_items += 1
            a, b = item[1], item[2]
            dx = float(b.x - a.x)
            dy = float(b.y - a.y)
            length = math.hypot(dx, dy)

            if length < geom.vector_min_segment_length_pt:
                continue

            major = max(abs(dx), abs(dy), 1.0)
            if min(abs(dx), abs(dy)) > (
                geom.vector_orthogonality_tolerance * major
            ):
                continue

            if (
                max(a.x, b.x) < border_margin
                or min(a.x, b.x) > page_w - border_margin
                or max(a.y, b.y) < border_margin
                or min(a.y, b.y) > page_h - border_margin
            ):
                continue

            if abs(dx) >= abs(dy):
                orientation = "H"
                y = (float(a.y) + float(b.y)) / 2.0
                x1, x2 = sorted((float(a.x), float(b.x)))
                p1, p2 = (x1, y), (x2, y)
            else:
                orientation = "V"
                x = (float(a.x) + float(b.x)) / 2.0
                y1, y2 = sorted((float(a.y), float(b.y)))
                p1, p2 = (x, y1), (x, y2)

            seg = VectorSegment(
                segment_id=next_id,
                orientation=orientation,
                p1=p1,
                p2=p2,
                length_pt=length,
                color_name=cname,
                rgb=rgb,
                stroke_width=stroke_width,
                drawing_index=drawing_idx,
                source_item_index=item_idx,
                is_near_black=near_black,
            )
            next_id += 1

            p = profile[cname]
            p["count"] += 1
            p["total_length_pt"] += length
            p["horizontal"] += int(orientation == "H")
            p["vertical"] += int(orientation == "V")

            if near_black:
                relevant_black_items += 1
                if relevant_black_items > geom.max_near_black_line_items:
                    truncated = True
                    break
                accepted.append(seg)
                if len(accepted) >= geom.max_candidate_segments:
                    truncated = True
                    break
            elif cname not in {"NONE", "OTHER"}:
                colored_inventory[cname].append(seg)

        if truncated:
            break

    profile_out = {
        name: {
            "qualifying_orthogonal_segments": int(v["count"]),
            "horizontal_segments": int(v["horizontal"]),
            "vertical_segments": int(v["vertical"]),
            "total_length_pt": round(float(v["total_length_pt"]), 2),
        }
        for name, v in sorted(
            profile.items(),
            key=lambda kv: kv[1]["count"],
            reverse=True,
        )
    }

    return {
        "status": "OK",
        "page_width_pt": page_w,
        "page_height_pt": page_h,
        "drawing_path_count": len(drawings),
        "line_items_scanned": total_line_items,
        "near_black_line_items_scanned": relevant_black_items,
        "accepted_segments": accepted,
        "colored_inventory": dict(colored_inventory),
        "profile_by_stroke_color": profile_out,
        "scan_truncated": truncated,
        "processing_seconds": round(time.perf_counter() - t0, 4),
    }
