from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PaperSpec:
    name: str
    width_mm: float
    height_mm: float


PAPERS: dict[str, PaperSpec] = {
    # US Letter: 8.5in x 11in
    "letter": PaperSpec("letter", 215.9, 279.4),
    "a4": PaperSpec("a4", 210.0, 297.0),
}


def get_paper(name: str) -> PaperSpec:
    key = name.strip().lower()
    if key not in PAPERS:
        raise ValueError(f"Unknown paper '{name}'. Expected one of: {', '.join(sorted(PAPERS))}")
    return PAPERS[key]


def mm_to_points(mm: float) -> float:
    # 1 inch = 25.4mm; 1 point = 1/72 inch
    return (mm / 25.4) * 72.0

