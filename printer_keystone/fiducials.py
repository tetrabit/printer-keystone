from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

import numpy as np


@dataclass(frozen=True)
class FiducialLayout:
    # marker_id -> (x_mm, y_mm) marker CENTER in "paper coordinates"
    centers_mm: Dict[int, Tuple[float, float]]
    marker_size_mm: float
    margin_mm: float


def default_layout(width_mm: float, height_mm: float, *, marker_size_mm: float = 22.0, margin_mm: float = 12.0) -> FiducialLayout:
    # Paper coordinates: origin at top-left, +x right, +y down.
    # IDs chosen to be stable and easy to distinguish.
    centers = {
        10: (margin_mm + marker_size_mm / 2.0, margin_mm + marker_size_mm / 2.0),  # TL
        11: (width_mm - margin_mm - marker_size_mm / 2.0, margin_mm + marker_size_mm / 2.0),  # TR
        12: (width_mm - margin_mm - marker_size_mm / 2.0, height_mm - margin_mm - marker_size_mm / 2.0),  # BR
        13: (margin_mm + marker_size_mm / 2.0, height_mm - margin_mm - marker_size_mm / 2.0),  # BL
        14: (width_mm / 2.0, height_mm / 2.0),  # center (helps stability)
    }
    return FiducialLayout(centers_mm=centers, marker_size_mm=marker_size_mm, margin_mm=margin_mm)


def aruco_dictionary_name() -> str:
    # OpenCV dictionary for stable detection.
    return "DICT_4X4_250"


def generate_aruco_marker_png_bytes(marker_id: int, px: int = 800) -> bytes:
    import cv2

    aruco = cv2.aruco
    d = aruco.getPredefinedDictionary(getattr(aruco, aruco_dictionary_name()))
    img = aruco.generateImageMarker(d, marker_id, px)
    ok, buf = cv2.imencode(".png", img)
    if not ok:
        raise RuntimeError("cv2.imencode failed for marker image")
    return bytes(buf)


def detect_aruco_markers(bgr: np.ndarray) -> dict[int, np.ndarray]:
    """
    Returns: marker_id -> corners (4,2) float32 in image pixel coords.
    Corners are in OpenCV ArUco order (clockwise).
    """
    import cv2

    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    aruco = cv2.aruco
    d = aruco.getPredefinedDictionary(getattr(aruco, aruco_dictionary_name()))
    params = aruco.DetectorParameters()
    detector = aruco.ArucoDetector(d, params)
    corners, ids, _rejected = detector.detectMarkers(gray)
    out: dict[int, np.ndarray] = {}
    if ids is None:
        return out
    for c, mid in zip(corners, ids.flatten()):
        out[int(mid)] = c.reshape(4, 2).astype(np.float32)
    return out


def marker_centers(corners_by_id: dict[int, np.ndarray]) -> dict[int, tuple[float, float]]:
    centers: dict[int, tuple[float, float]] = {}
    for mid, corners in corners_by_id.items():
        cx = float(corners[:, 0].mean())
        cy = float(corners[:, 1].mean())
        centers[mid] = (cx, cy)
    return centers

