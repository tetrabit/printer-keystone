from __future__ import annotations

import io
from pathlib import Path
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from .fiducials import default_layout, generate_aruco_marker_png_bytes
from .paper import get_paper, mm_to_points


def _draw_crosshair(c: canvas.Canvas, x_pt: float, y_pt: float, r_pt: float = 10.0) -> None:
    c.saveState()
    c.setLineWidth(0.8)
    c.line(x_pt - r_pt, y_pt, x_pt + r_pt, y_pt)
    c.line(x_pt, y_pt - r_pt, x_pt, y_pt + r_pt)
    c.restoreState()


def generate_calibration_pdf(
    out_path: str | Path,
    *,
    paper: str = "letter",
    safe_inset_mm: float = 12.0,
    marker_size_mm: float = 22.0,
    marker_margin_mm: float | None = None,
    border_inset_mm: float | None = None,
) -> Path:
    """
    Generates a 2-page PDF:
      page 1: front
      page 2: back

    Paper coordinates used in analysis are "front-view": origin top-left.
    The analysis step uses marker IDs + paper edges to map both scans into a consistent "front-view" coordinate system.
    """
    p = get_paper(paper)
    width_pt = mm_to_points(p.width_mm)
    height_pt = mm_to_points(p.height_mm)

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    c = canvas.Canvas(str(out), pagesize=(width_pt, height_pt))

    # safe_inset_mm: distance from paper edge to the printed border.
    # marker_margin_mm: distance from paper edge to marker outer edge; keep it >= border inset + clearance.
    border_inset_mm = safe_inset_mm if border_inset_mm is None else float(border_inset_mm)
    clearance_mm = 3.0
    marker_margin_mm = (
        max(float(marker_margin_mm), border_inset_mm + clearance_mm) if marker_margin_mm is not None else (border_inset_mm + clearance_mm)
    )

    layout = default_layout(p.width_mm, p.height_mm, marker_size_mm=float(marker_size_mm), margin_mm=float(marker_margin_mm))

    def draw_side(side: str) -> None:
        c.setTitle("printer-keystone calibration")
        # Add a light border to help paper-edge detection.
        c.saveState()
        c.setLineWidth(0.5)
        inset = mm_to_points(border_inset_mm)
        c.rect(inset, inset, width_pt - 2 * inset, height_pt - 2 * inset)
        c.restoreState()

        # Crosshair at the center.
        cx_pt = width_pt / 2.0
        cy_pt = height_pt / 2.0
        _draw_crosshair(c, cx_pt, cy_pt, r_pt=mm_to_points(6.0))

        # Draw markers.
        size_pt = mm_to_points(layout.marker_size_mm)
        for mid, (x_mm, y_mm) in layout.centers_mm.items():
            # Convert from paper coords (top-left origin, +y down) to ReportLab coords (bottom-left, +y up).
            x_pt = mm_to_points(x_mm) - size_pt / 2.0
            y_pt = height_pt - mm_to_points(y_mm) - size_pt / 2.0

            png = generate_aruco_marker_png_bytes(mid, px=800)
            c.drawImage(ImageReader(io.BytesIO(png)), x_pt, y_pt, width=size_pt, height=size_pt, mask="auto")

            # small label
            c.setFont("Helvetica", 7)
            c.drawString(x_pt, y_pt - mm_to_points(2.8), f"id={mid}")

        # Header/instructions: keep them inside the safe area and to the right of the top-left marker.
        text_x_mm = marker_margin_mm + layout.marker_size_mm + 6.0
        title_y_mm = border_inset_mm + 6.0
        instr_y_mm = title_y_mm + 6.0
        c.setFont("Helvetica", 10)
        c.drawString(mm_to_points(text_x_mm), height_pt - mm_to_points(title_y_mm), f"{side.upper()} - paper={p.name}")
        c.setFont("Helvetica", 8)
        c.drawString(
            mm_to_points(text_x_mm),
            height_pt - mm_to_points(instr_y_mm),
            "Print at 100% scale (no fit-to-page). Then scan with full paper edges visible.",
        )

    # Front
    draw_side("front")
    c.showPage()

    # Back (same layout). The analysis step uses marker IDs to map the scan into the same
    # "front-view" coordinate system, regardless of how the paper is flipped.
    draw_side("back")
    c.showPage()

    c.save()
    return out
