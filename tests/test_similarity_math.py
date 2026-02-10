import numpy as np


def _apply_similarity(pts, scale, rot_deg, tx, ty):
    th = np.deg2rad(rot_deg)
    R = np.array([[np.cos(th), -np.sin(th)], [np.sin(th), np.cos(th)]], dtype=float)
    return (scale * (pts @ R.T)) + np.array([tx, ty], dtype=float)


def test_similarity_estimation_import_only():
    # Smoke-test import path; algorithm is exercised by higher-level usage.
    import printer_keystone.analyze  # noqa: F401

