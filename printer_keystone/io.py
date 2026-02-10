from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import numpy as np


@dataclass(frozen=True)
class LoadedImage:
    path: Path
    page_index: int  # 0-based
    bgr: np.ndarray  # OpenCV BGR


def _load_pdf_page_to_bgr(path: Path, page_index: int, dpi: int) -> np.ndarray:
    import fitz  # PyMuPDF
    import cv2

    doc = fitz.open(str(path))
    if page_index < 0 or page_index >= doc.page_count:
        raise ValueError(f"{path} has {doc.page_count} pages; requested page {page_index + 1}")
    page = doc.load_page(page_index)
    mat = fitz.Matrix(dpi / 72.0, dpi / 72.0)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
    # PyMuPDF gives RGB; OpenCV expects BGR
    return cv2.cvtColor(img, cv2.COLOR_RGB2BGR)


def load_image_or_pdf(path: str | Path, page: int = 1, dpi: int = 300) -> LoadedImage:
    import cv2

    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(str(p))

    page_index = page - 1
    if p.suffix.lower() == ".pdf":
        bgr = _load_pdf_page_to_bgr(p, page_index=page_index, dpi=dpi)
        return LoadedImage(path=p, page_index=page_index, bgr=bgr)

    bgr = cv2.imread(str(p), cv2.IMREAD_COLOR)
    if bgr is None:
        raise ValueError(f"Failed to read image: {p}")
    return LoadedImage(path=p, page_index=0, bgr=bgr)


def ensure_dir(path: Optional[str | Path]) -> Optional[Path]:
    if path is None:
        return None
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p

