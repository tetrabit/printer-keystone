from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from .analyze import analyze_duplex
from .generate import generate_calibration_pdf
from .io import ensure_dir, load_image_or_pdf
from .paper import PAPERS

app = typer.Typer(add_completion=False)


@app.command()
def generate(
    out: Path = typer.Option(Path("calibration.pdf"), "--out", help="Output PDF path."),
    paper: str = typer.Option("letter", "--paper", help=f"Paper size. One of: {', '.join(sorted(PAPERS))}"),
) -> None:
    pdf = generate_calibration_pdf(out, paper=paper)
    typer.echo(str(pdf))


@app.command()
def analyze(
    front: Path = typer.Option(..., "--front", help="Front scan image/PDF."),
    back: Path = typer.Option(..., "--back", help="Back scan image/PDF."),
    front_page: int = typer.Option(1, "--front-page", help="If --front is a PDF, 1-based page number to use."),
    back_page: int = typer.Option(1, "--back-page", help="If --back is a PDF, 1-based page number to use."),
    dpi: int = typer.Option(300, "--dpi", help="DPI when rasterizing PDFs for analysis."),
    paper: str = typer.Option("letter", "--paper", help=f"Paper size. One of: {', '.join(sorted(PAPERS))}"),
    debug_dir: Optional[Path] = typer.Option(None, "--debug-dir", help="If set, writes debug images here."),
) -> None:
    dbg = ensure_dir(debug_dir)
    front_img = load_image_or_pdf(front, page=front_page, dpi=dpi)
    back_img = load_image_or_pdf(back, page=back_page, dpi=dpi)

    res = analyze_duplex(front_bgr=front_img.bgr, back_bgr=back_img.bgr, paper=paper, debug_dir=dbg)

    dx, dy = res.back_shift_mm
    def lr(val: float) -> str:
        if val >= 0:
            return f"right {val:.2f} mm"
        return f"left {abs(val):.2f} mm"

    def ud(val: float) -> str:
        if val >= 0:
            return f"down {val:.2f} mm"
        return f"up {abs(val):.2f} mm"

    typer.echo("Back-side shift to align to front (front-view coordinates):")
    typer.echo(f"  back_shift_x_mm: {dx:.2f}  ({lr(dx)})")
    typer.echo(f"  back_shift_y_mm: {dy:.2f}  ({ud(dy)})")
    typer.echo("")
    typer.echo("Diagnostics:")
    typer.echo(f"  front: translation_mm=({res.front.translation_mm[0]:.2f}, {res.front.translation_mm[1]:.2f}) rot_deg={res.front.rotation_deg:.3f} scale={res.front.scale:.6f} coord_fix={res.front.coord_fix} markers={res.front.used_marker_ids}")
    typer.echo(f"  back:  translation_mm=({res.back.translation_mm[0]:.2f}, {res.back.translation_mm[1]:.2f}) rot_deg={res.back.rotation_deg:.3f} scale={res.back.scale:.6f} coord_fix={res.back.coord_fix} markers={res.back.used_marker_ids}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
