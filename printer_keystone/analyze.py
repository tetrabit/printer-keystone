from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

from .fiducials import default_layout, detect_aruco_markers, marker_centers
from .paper import get_paper
from .vision import map_points_px_to_mm, paper_homography_px_to_mm


@dataclass(frozen=True)
class SideResult:
    paper: str
    translation_mm: tuple[float, float]  # dx, dy of printed content relative to ideal
    rotation_deg: float
    scale: float
    used_marker_ids: list[int]
    coord_fix: str


def _estimate_similarity(ideal_mm: np.ndarray, measured_mm: np.ndarray) -> tuple[np.ndarray, list[int]]:
    import cv2

    if ideal_mm.shape[0] < 3:
        raise ValueError("Need at least 3 points to estimate print placement")

    # estimateAffinePartial2D maps src->dst: ideal -> measured
    M, inliers = cv2.estimateAffinePartial2D(
        ideal_mm.astype(np.float32),
        measured_mm.astype(np.float32),
        method=cv2.RANSAC,
        ransacReprojThreshold=2.0,  # mm
        maxIters=5000,
        confidence=0.999,
    )
    if M is None:
        raise ValueError("Failed to estimate placement transform")

    inlier_idx: list[int] = []
    if inliers is not None:
        for i, v in enumerate(inliers.flatten().tolist()):
            if int(v) == 1:
                inlier_idx.append(i)
    else:
        inlier_idx = list(range(ideal_mm.shape[0]))

    return M.astype(np.float64), inlier_idx


def _best_coord_symmetry(
    pts_mm: np.ndarray,
    ids: list[int],
    *,
    width_mm: float,
    height_mm: float,
    ideal_by_id: dict[int, tuple[float, float]],
) -> tuple[np.ndarray, str]:
    """
    Fixes common scan orientation issues by choosing the symmetry of the page rectangle that best
    matches marker IDs to their expected locations.
    """
    if len(ids) < 3:
        return pts_mm, "none"

    ideal = np.array([ideal_by_id[mid] for mid in ids], dtype=np.float64)

    def identity(p):
        return p

    def mirror_x(p):
        q = p.copy()
        q[:, 0] = width_mm - q[:, 0]
        return q

    def mirror_y(p):
        q = p.copy()
        q[:, 1] = height_mm - q[:, 1]
        return q

    def rot180(p):
        q = p.copy()
        q[:, 0] = width_mm - q[:, 0]
        q[:, 1] = height_mm - q[:, 1]
        return q

    candidates = [
        ("identity", identity),
        ("mirror_x", mirror_x),
        ("mirror_y", mirror_y),
        ("rot180", rot180),
    ]

    best_name = "identity"
    best_pts = pts_mm
    best_score = float("inf")
    for name, fn in candidates:
        q = fn(pts_mm)
        score = float(np.mean(np.sum((q - ideal) ** 2, axis=1)))
        if score < best_score:
            best_score = score
            best_name = name
            best_pts = q
    return best_pts, best_name


def analyze_side(
    bgr: np.ndarray,
    *,
    paper: str,
    marker_size_mm: float = 22.0,
    marker_margin_mm: float = 15.0,
    border_inset_mm: Optional[float] = None,
    debug_dir: Optional[Path] = None,
    debug_tag: str = "front",
) -> SideResult:
    import cv2

    ps = get_paper(paper)
    layout = default_layout(ps.width_mm, ps.height_mm, marker_size_mm=float(marker_size_mm), margin_mm=float(marker_margin_mm))

    det = paper_homography_px_to_mm(
        bgr,
        width_mm=ps.width_mm,
        height_mm=ps.height_mm,
        border_inset_mm=border_inset_mm,
        debug_dir=debug_dir,
        debug_tag=debug_tag,
    )

    markers = detect_aruco_markers(bgr)
    centers_px = marker_centers(markers)

    # Filter to known IDs and keep stable ordering.
    want_ids = [10, 11, 12, 13, 14]
    have_ids = [mid for mid in want_ids if mid in centers_px]
    if len(have_ids) < 3:
        raise ValueError(f"{debug_tag}: found only {len(have_ids)} fiducials; need >=3. Found IDs: {sorted(centers_px)}")

    pts_px = np.array([centers_px[mid] for mid in have_ids], dtype=np.float64)
    pts_mm = map_points_px_to_mm(det.homography_px_to_mm, pts_px)

    ideal_mm = np.array([layout.centers_mm[mid] for mid in have_ids], dtype=np.float64)

    pts_mm_fixed, coord_fix = _best_coord_symmetry(
        pts_mm,
        have_ids,
        width_mm=ps.width_mm,
        height_mm=ps.height_mm,
        ideal_by_id=layout.centers_mm,
    )

    M, inlier_idx = _estimate_similarity(ideal_mm, pts_mm_fixed)

    a, b, tx = float(M[0, 0]), float(M[0, 1]), float(M[0, 2])
    c, d, ty = float(M[1, 0]), float(M[1, 1]), float(M[1, 2])
    scale = float((a * a + c * c) ** 0.5)
    rot_rad = float(np.arctan2(c, a))
    rot_deg = rot_rad * 180.0 / np.pi

    if debug_dir is not None:
        dbg = bgr.copy()
        # draw marker centers + ID
        for mid, (cx, cy) in centers_px.items():
            cv2.circle(dbg, (int(cx), int(cy)), 10, (0, 255, 0), 2)
            cv2.putText(dbg, str(mid), (int(cx) + 12, int(cy) + 12), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        cv2.imwrite(str(debug_dir / f"{debug_tag}_markers.png"), dbg)

    used_ids = [have_ids[i] for i in inlier_idx] if inlier_idx else have_ids
    return SideResult(
        paper=ps.name,
        translation_mm=(tx, ty),
        rotation_deg=rot_deg,
        scale=scale,
        used_marker_ids=used_ids,
        coord_fix=coord_fix,
    )


@dataclass(frozen=True)
class DuplexResult:
    front: SideResult
    back: SideResult
    back_shift_mm: tuple[float, float]  # shift to apply to back so it matches front


def analyze_duplex(
    *,
    front_bgr: np.ndarray,
    back_bgr: np.ndarray,
    paper: str,
    marker_size_mm: float = 22.0,
    marker_margin_mm: float = 15.0,
    border_inset_mm: Optional[float] = None,
    debug_dir: Optional[Path] = None,
) -> DuplexResult:
    front = analyze_side(
        front_bgr,
        paper=paper,
        marker_size_mm=marker_size_mm,
        marker_margin_mm=marker_margin_mm,
        border_inset_mm=border_inset_mm,
        debug_dir=debug_dir,
        debug_tag="front",
    )
    back = analyze_side(
        back_bgr,
        paper=paper,
        marker_size_mm=marker_size_mm,
        marker_margin_mm=marker_margin_mm,
        border_inset_mm=border_inset_mm,
        debug_dir=debug_dir,
        debug_tag="back",
    )

    dx = front.translation_mm[0] - back.translation_mm[0]
    dy = front.translation_mm[1] - back.translation_mm[1]
    return DuplexResult(front=front, back=back, back_shift_mm=(dx, dy))
