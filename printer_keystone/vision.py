from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

from .fiducials import detect_aruco_markers, marker_centers


@dataclass(frozen=True)
class PaperDetection:
    corners_px: np.ndarray  # (4,2) float32 in scan pixel coords; order: TL,TR,BR,BL in *canonical* sense if labeled
    homography_px_to_mm: np.ndarray  # (3,3)
    labeled: bool


def _order_points_tl_tr_br_bl(pts: np.ndarray) -> np.ndarray:
    # pts: (4,2)
    s = pts.sum(axis=1)
    diff = np.diff(pts, axis=1).reshape(-1)
    tl = pts[np.argmin(s)]
    br = pts[np.argmax(s)]
    tr = pts[np.argmin(diff)]
    bl = pts[np.argmax(diff)]
    return np.stack([tl, tr, br, bl], axis=0).astype(np.float32)


def detect_paper_quad_corners(bgr: np.ndarray) -> np.ndarray:
    """
    Returns 4 corners in pixel coords (unordered).
    Best-effort detection; will pick the largest contour.
    """
    import cv2

    h, w = bgr.shape[:2]
    img_area = float(h * w)

    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(gray, 40, 140)
    edges = cv2.dilate(edges, None, iterations=2)

    contours, _hier = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        # Common when the scan background is uniformly white and the paper edge isn't visible.
        return np.array([[0.0, 0.0], [float(w - 1), 0.0], [float(w - 1), float(h - 1)], [0.0, float(h - 1)]], dtype=np.float32)

    contour = max(contours, key=cv2.contourArea)
    area = float(cv2.contourArea(contour))
    # If the largest contour is too small relative to the whole image, it's likely a fiducial or other
    # printed object. In that case, treat the image bounds as the paper bounds (many scanners/PDFs
    # are already cropped to the page).
    if area < 10_000 or (area / img_area) < 0.25:
        return np.array([[0.0, 0.0], [float(w - 1), 0.0], [float(w - 1), float(h - 1)], [0.0, float(h - 1)]], dtype=np.float32)

    # If the largest contour is a large inset rectangle (common when a printed border is the strongest edge),
    # prefer image bounds as the paper bounds.
    x, y, bw, bh = cv2.boundingRect(contour)
    inset_l = float(x) / float(w)
    inset_t = float(y) / float(h)
    inset_r = float(w - (x + bw)) / float(w)
    inset_b = float(h - (y + bh)) / float(h)
    if (area / img_area) > 0.75 and min(inset_l, inset_t, inset_r, inset_b) > 0.04:
        return np.array([[0.0, 0.0], [float(w - 1), 0.0], [float(w - 1), float(h - 1)], [0.0, float(h - 1)]], dtype=np.float32)

    peri = cv2.arcLength(contour, True)
    approx = cv2.approxPolyDP(contour, 0.02 * peri, True)
    if len(approx) == 4:
        return approx.reshape(4, 2).astype(np.float32)

    rect = cv2.minAreaRect(contour)
    box = cv2.boxPoints(rect)
    return box.astype(np.float32)


def _label_corners_using_markers(
    corners_px_unordered: np.ndarray,
    corner_marker_centers_px: dict[int, tuple[float, float]],
    *,
    max_dist_px: float,
) -> Optional[np.ndarray]:
    """
    If all 4 corner marker IDs (10..13) are present and each corner is close to one, return ordered corners TL,TR,BR,BL.
    Else return None.
    """
    # canonical marker->corner index mapping
    want = {10: 0, 11: 1, 12: 2, 13: 3}
    have = {mid: np.array([cx, cy], dtype=np.float32) for mid, (cx, cy) in corner_marker_centers_px.items() if mid in want}
    if len(have) < 4:
        return None

    corners = corners_px_unordered.astype(np.float32)
    assigned: dict[int, int] = {}  # marker_id -> corner_idx
    used_corners: set[int] = set()

    for mid, mpt in have.items():
        dists = np.linalg.norm(corners - mpt[None, :], axis=1)
        ci = int(np.argmin(dists))
        if float(dists[ci]) > max_dist_px:
            return None
        if ci in used_corners:
            return None
        assigned[mid] = ci
        used_corners.add(ci)

    ordered = np.zeros((4, 2), dtype=np.float32)
    for mid, corner_pos in want.items():
        ordered[corner_pos] = corners[assigned[mid]]
    return ordered


def paper_homography_px_to_mm(
    bgr: np.ndarray,
    *,
    width_mm: float,
    height_mm: float,
    debug_dir: Optional[Path] = None,
    debug_tag: str = "page",
) -> PaperDetection:
    """
    Detect paper edges and compute a homography to canonical "paper mm coords":
      origin at top-left, +x right, +y down.
    """
    import cv2

    corners_unordered = detect_paper_quad_corners(bgr)

    markers = detect_aruco_markers(bgr)
    centers = marker_centers(markers)

    # Use marker IDs to label corners if possible; otherwise geometric ordering.
    h, w = bgr.shape[:2]
    max_dist_px = 0.20 * float(max(w, h))
    labeled = False
    corners_px = _label_corners_using_markers(corners_unordered, centers, max_dist_px=max_dist_px)
    if corners_px is None:
        corners_px = _order_points_tl_tr_br_bl(corners_unordered)
    else:
        labeled = True

    # Destination corners in mm (canonical)
    dst = np.array(
        [
            [0.0, 0.0],
            [width_mm, 0.0],
            [width_mm, height_mm],
            [0.0, height_mm],
        ],
        dtype=np.float32,
    )

    H = cv2.getPerspectiveTransform(corners_px.astype(np.float32), dst)

    if debug_dir is not None:
        dbg = bgr.copy()
        for i, (x, y) in enumerate(corners_px):
            cv2.circle(dbg, (int(x), int(y)), 12, (0, 0, 255), 2)
            cv2.putText(dbg, str(i), (int(x) + 10, int(y) + 10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)
        cv2.imwrite(str(debug_dir / f"{debug_tag}_paper_corners.png"), dbg)

    return PaperDetection(corners_px=corners_px.astype(np.float32), homography_px_to_mm=H.astype(np.float64), labeled=labeled)


def map_points_px_to_mm(H_px_to_mm: np.ndarray, pts_px: np.ndarray) -> np.ndarray:
    import cv2

    pts = pts_px.reshape(-1, 1, 2).astype(np.float32)
    out = cv2.perspectiveTransform(pts, H_px_to_mm.astype(np.float64))
    return out.reshape(-1, 2).astype(np.float64)
