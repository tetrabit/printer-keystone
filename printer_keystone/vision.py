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
    method: str  # edges|image_bounds|border


def _order_points_tl_tr_br_bl(pts: np.ndarray) -> np.ndarray:
    # pts: (4,2)
    s = pts.sum(axis=1)
    diff = np.diff(pts, axis=1).reshape(-1)
    tl = pts[np.argmin(s)]
    br = pts[np.argmax(s)]
    tr = pts[np.argmin(diff)]
    bl = pts[np.argmax(diff)]
    return np.stack([tl, tr, br, bl], axis=0).astype(np.float32)


def detect_paper_quad_corners(bgr: np.ndarray) -> tuple[np.ndarray, str]:
    """
    Returns 4 corners in pixel coords (unordered) and a method string.
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
        return (
            np.array([[0.0, 0.0], [float(w - 1), 0.0], [float(w - 1), float(h - 1)], [0.0, float(h - 1)]], dtype=np.float32),
            "image_bounds",
        )

    contour = max(contours, key=cv2.contourArea)
    area = float(cv2.contourArea(contour))
    # If the largest contour is too small relative to the whole image, it's likely a fiducial or other
    # printed object. In that case, treat the image bounds as the paper bounds (many scanners/PDFs
    # are already cropped to the page).
    if area < 10_000 or (area / img_area) < 0.25:
        return (
            np.array([[0.0, 0.0], [float(w - 1), 0.0], [float(w - 1), float(h - 1)], [0.0, float(h - 1)]], dtype=np.float32),
            "image_bounds",
        )

    # If the largest contour is a large inset rectangle, it may be the printed border (not the paper edge).
    # Only prefer image bounds when the scan appears to already be cropped to the page (no dark background
    # visible outside the paper).
    x, y, bw, bh = cv2.boundingRect(contour)
    inset_l = float(x) / float(w)
    inset_t = float(y) / float(h)
    inset_r = float(w - (x + bw)) / float(w)
    inset_b = float(h - (y + bh)) / float(h)
    if (area / img_area) > 0.75 and min(inset_l, inset_t, inset_r, inset_b) > 0.03:
        # Sample the outer strip; if it's nearly white, the scan is likely already cropped to the page.
        strip = max(4, int(round(0.02 * min(h, w))))
        border_pixels = np.concatenate(
            [
                gray[:strip, :].reshape(-1),
                gray[-strip:, :].reshape(-1),
                gray[:, :strip].reshape(-1),
                gray[:, -strip:].reshape(-1),
            ]
        )
        if float(np.mean(border_pixels)) > 245.0:
            return (
                np.array([[0.0, 0.0], [float(w - 1), 0.0], [float(w - 1), float(h - 1)], [0.0, float(h - 1)]], dtype=np.float32),
                "image_bounds",
            )

    peri = cv2.arcLength(contour, True)
    approx = cv2.approxPolyDP(contour, 0.02 * peri, True)
    if len(approx) == 4:
        return approx.reshape(4, 2).astype(np.float32), "edges"

    rect = cv2.minAreaRect(contour)
    box = cv2.boxPoints(rect)
    return box.astype(np.float32), "edges"


def _mask_out_markers(gray: np.ndarray, markers: dict[int, np.ndarray], pad_px: int = 10) -> np.ndarray:
    import cv2

    out = gray.copy()
    for corners in markers.values():
        xs = corners[:, 0]
        ys = corners[:, 1]
        x0 = max(int(xs.min()) - pad_px, 0)
        y0 = max(int(ys.min()) - pad_px, 0)
        x1 = min(int(xs.max()) + pad_px, out.shape[1] - 1)
        y1 = min(int(ys.max()) + pad_px, out.shape[0] - 1)
        cv2.rectangle(out, (x0, y0), (x1, y1), 255, thickness=-1)
    return out


def detect_border_quad_corners(bgr: np.ndarray, *, debug_dir: Optional[Path] = None, debug_tag: str = "page") -> Optional[np.ndarray]:
    """
    Best-effort detection of the printed inset border rectangle (if present).

    Returns corners in px coords, ordered TL,TR,BR,BL if successful; else None.
    """
    import cv2

    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    markers = detect_aruco_markers(bgr)
    gray2 = _mask_out_markers(gray, markers, pad_px=18) if markers else gray

    # Emphasize the thin border line.
    edges = cv2.Canny(gray2, 40, 140)
    edges = cv2.dilate(edges, None, iterations=1)

    lines = cv2.HoughLinesP(edges, 1, np.pi / 180.0, threshold=120, minLineLength=int(min(bgr.shape[:2]) * 0.3), maxLineGap=20)
    if lines is None:
        return None

    # Classify segments.
    horiz: list[tuple[int, int, int, int]] = []
    vert: list[tuple[int, int, int, int]] = []
    for (x1, y1, x2, y2) in lines.reshape(-1, 4):
        dx = float(x2 - x1)
        dy = float(y2 - y1)
        ang = abs(np.degrees(np.arctan2(dy, dx)))
        if ang < 15.0 or ang > 165.0:
            horiz.append((x1, y1, x2, y2))
        elif 75.0 < ang < 105.0:
            vert.append((x1, y1, x2, y2))

    if len(horiz) < 2 or len(vert) < 2:
        return None

    # Pick top/bottom by y, left/right by x.
    def seg_y(s):  # mean y
        return 0.5 * (s[1] + s[3])

    def seg_x(s):  # mean x
        return 0.5 * (s[0] + s[2])

    top_y = np.percentile([seg_y(s) for s in horiz], 10)
    bot_y = np.percentile([seg_y(s) for s in horiz], 90)
    left_x = np.percentile([seg_x(s) for s in vert], 10)
    right_x = np.percentile([seg_x(s) for s in vert], 90)

    top = [s for s in horiz if seg_y(s) <= top_y + 10]
    bottom = [s for s in horiz if seg_y(s) >= bot_y - 10]
    left = [s for s in vert if seg_x(s) <= left_x + 10]
    right = [s for s in vert if seg_x(s) >= right_x - 10]

    def fit_line(segs: list[tuple[int, int, int, int]]) -> Optional[tuple[float, float, float]]:
        if not segs:
            return None
        pts = []
        for x1, y1, x2, y2 in segs:
            pts.append([x1, y1])
            pts.append([x2, y2])
        pts_np = np.array(pts, dtype=np.float32)
        vx, vy, x0, y0 = cv2.fitLine(pts_np, cv2.DIST_L2, 0, 0.01, 0.01).flatten().tolist()
        # Convert point+direction to ax+by+c=0
        a = float(vy)
        b = float(-vx)
        c = float(-(a * x0 + b * y0))
        norm = (a * a + b * b) ** 0.5
        if norm < 1e-9:
            return None
        return a / norm, b / norm, c / norm

    def intersect(l1: tuple[float, float, float], l2: tuple[float, float, float]) -> Optional[tuple[float, float]]:
        a1, b1, c1 = l1
        a2, b2, c2 = l2
        det = a1 * b2 - a2 * b1
        if abs(det) < 1e-9:
            return None
        x = (b1 * c2 - b2 * c1) / det
        y = (c1 * a2 - c2 * a1) / det
        return float(x), float(y)

    lt = fit_line(top)
    lb = fit_line(bottom)
    ll = fit_line(left)
    lr = fit_line(right)
    if not (lt and lb and ll and lr):
        return None

    p_tl = intersect(lt, ll)
    p_tr = intersect(lt, lr)
    p_br = intersect(lb, lr)
    p_bl = intersect(lb, ll)
    if not (p_tl and p_tr and p_br and p_bl):
        return None

    corners = np.array([p_tl, p_tr, p_br, p_bl], dtype=np.float32)

    if debug_dir is not None:
        dbg = cv2.cvtColor(gray2, cv2.COLOR_GRAY2BGR)
        for x1, y1, x2, y2 in top + bottom + left + right:
            cv2.line(dbg, (x1, y1), (x2, y2), (0, 255, 255), 2)
        for i, (x, y) in enumerate(corners):
            cv2.circle(dbg, (int(x), int(y)), 12, (0, 0, 255), 2)
            cv2.putText(dbg, str(i), (int(x) + 10, int(y) + 10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)
        cv2.imwrite(str(debug_dir / f"{debug_tag}_border_corners.png"), dbg)

    return corners


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
    border_inset_mm: Optional[float] = None,
    debug_dir: Optional[Path] = None,
    debug_tag: str = "page",
) -> PaperDetection:
    """
    Detect paper edges and compute a homography to canonical "paper mm coords":
      origin at top-left, +x right, +y down.
    """
    import cv2

    markers = detect_aruco_markers(bgr)
    centers = marker_centers(markers)

    border_inset_mm_f = None if border_inset_mm is None else float(border_inset_mm)
    if border_inset_mm_f is not None:
        # Prefer the printed border quad when available: it is present even when the scan is cropped
        # and the physical paper edge is invisible. If border detection fails, fall back to paper edges.
        border = detect_border_quad_corners(bgr, debug_dir=debug_dir, debug_tag=debug_tag)
        if border is not None:
            corners_unordered = border.astype(np.float32)
            method = "border"
        else:
            corners_unordered, method = detect_paper_quad_corners(bgr)
    else:
        corners_unordered, method = detect_paper_quad_corners(bgr)

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
    if method == "border" and border_inset_mm_f is not None:
        dst = np.array(
            [
                [border_inset_mm_f, border_inset_mm_f],
                [width_mm - border_inset_mm_f, border_inset_mm_f],
                [width_mm - border_inset_mm_f, height_mm - border_inset_mm_f],
                [border_inset_mm_f, height_mm - border_inset_mm_f],
            ],
            dtype=np.float32,
        )
    else:
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

    return PaperDetection(corners_px=corners_px.astype(np.float32), homography_px_to_mm=H.astype(np.float64), labeled=labeled, method=method)


def map_points_px_to_mm(H_px_to_mm: np.ndarray, pts_px: np.ndarray) -> np.ndarray:
    import cv2

    pts = pts_px.reshape(-1, 1, 2).astype(np.float32)
    out = cv2.perspectiveTransform(pts, H_px_to_mm.astype(np.float64))
    return out.reshape(-1, 2).astype(np.float64)
