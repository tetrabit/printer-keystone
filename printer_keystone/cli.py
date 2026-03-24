from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

from .analyze import analyze_duplex
from .generate import generate_calibration_pdf, generate_verify_pdf
from .io import ensure_dir, load_image_or_pdf
from .paper import PAPERS

RESULT_FILE = Path("calibration_result.json")

app = typer.Typer(add_completion=False)


@app.command()
def generate(
    out: Path = typer.Option(Path("calibration.pdf"), "--out", help="Output PDF path."),
    paper: str = typer.Option("letter", "--paper", help=f"Paper size. One of: {', '.join(sorted(PAPERS))}"),
    safe_inset_mm: float = typer.Option(12.0, "--safe-inset-mm", help="Inset from paper edge for the printed border (mm)."),
    marker_size_mm: float = typer.Option(22.0, "--marker-size-mm", help="ArUco marker size (mm)."),
    marker_margin_mm: float = typer.Option(
        15.0,
        "--marker-margin-mm",
        help="Distance from paper edge to marker outer edge (mm). Should be >= safe inset + ~3mm.",
    ),
    border_inset_mm: Optional[float] = typer.Option(
        None,
        "--border-inset-mm",
        help="Inset from paper edge for the printed border (mm). Defaults to --safe-inset-mm.",
    ),
) -> None:
    pdf = generate_calibration_pdf(
        out,
        paper=paper,
        safe_inset_mm=safe_inset_mm,
        marker_size_mm=marker_size_mm,
        marker_margin_mm=marker_margin_mm,
        border_inset_mm=border_inset_mm,
    )
    typer.echo(str(pdf))


@app.command()
def analyze(
    front: Path = typer.Option(..., "--front", help="Front scan image/PDF."),
    back: Path = typer.Option(..., "--back", help="Back scan image/PDF."),
    front_page: int = typer.Option(1, "--front-page", help="If --front is a PDF, 1-based page number to use."),
    back_page: int = typer.Option(1, "--back-page", help="If --back is a PDF, 1-based page number to use."),
    dpi: int = typer.Option(300, "--dpi", help="DPI when rasterizing PDFs for analysis."),
    paper: str = typer.Option("letter", "--paper", help=f"Paper size. One of: {', '.join(sorted(PAPERS))}"),
    marker_size_mm: float = typer.Option(22.0, "--marker-size-mm", help="Marker size (mm) used when generating the calibration PDF."),
    marker_margin_mm: float = typer.Option(15.0, "--marker-margin-mm", help="Marker margin (mm) used when generating the calibration PDF."),
    border_inset_mm: Optional[float] = typer.Option(
        None,
        "--border-inset-mm",
        help="Border inset (mm) used when generating the calibration PDF. Helps if scans are cropped to the border.",
    ),
    debug_dir: Optional[Path] = typer.Option(None, "--debug-dir", help="If set, writes debug images here."),
    refine: bool = typer.Option(False, "--refine", help="Add measured residual to existing accumulated compensation."),
) -> None:
    dbg = ensure_dir(debug_dir)
    front_img = load_image_or_pdf(front, page=front_page, dpi=dpi)
    back_img = load_image_or_pdf(back, page=back_page, dpi=dpi)

    res = analyze_duplex(
        front_bgr=front_img.bgr,
        back_bgr=back_img.bgr,
        paper=paper,
        marker_size_mm=marker_size_mm,
        marker_margin_mm=marker_margin_mm,
        border_inset_mm=border_inset_mm,
        debug_dir=dbg,
    )

    dx, dy = res.back_shift_mm
    def lr(val: float) -> str:
        if val >= 0:
            return f"right {val:.2f} mm"
        return f"left {abs(val):.2f} mm"

    def ud(val: float) -> str:
        if val >= 0:
            return f"down {val:.2f} mm"
        return f"up {abs(val):.2f} mm"

    typer.echo("Measured offset (this scan):")
    typer.echo(f"  back_shift_x_mm: {dx:.2f}  ({lr(dx)})")
    typer.echo(f"  back_shift_y_mm: {dy:.2f}  ({ud(dy)})")
    typer.echo("")
    typer.echo("Diagnostics:")
    typer.echo(f"  front: translation_mm=({res.front.translation_mm[0]:.2f}, {res.front.translation_mm[1]:.2f}) rot_deg={res.front.rotation_deg:.3f} scale={res.front.scale:.6f} coord_fix={res.front.coord_fix} markers={res.front.used_marker_ids} reproj_err={res.front.reproj_error_mm:.3f}mm")
    typer.echo(f"  back:  translation_mm=({res.back.translation_mm[0]:.2f}, {res.back.translation_mm[1]:.2f}) rot_deg={res.back.rotation_deg:.3f} scale={res.back.scale:.6f} coord_fix={res.back.coord_fix} markers={res.back.used_marker_ids} reproj_err={res.back.reproj_error_mm:.3f}mm")

    # Accumulated per-side compensation: either fresh or refined.
    front_tx = res.front.translation_mm[0]
    front_ty = res.front.translation_mm[1]
    back_tx = res.back.translation_mm[0]
    back_ty = res.back.translation_mm[1]

    if refine and RESULT_FILE.exists():
        prev = json.loads(RESULT_FILE.read_text())
        prev_ftx = float(prev.get("accumulated_front_tx_mm", 0.0))
        prev_fty = float(prev.get("accumulated_front_ty_mm", 0.0))
        prev_btx = float(prev.get("accumulated_back_tx_mm", 0.0))
        prev_bty = float(prev.get("accumulated_back_ty_mm", 0.0))
        front_tx += prev_ftx
        front_ty += prev_fty
        back_tx += prev_btx
        back_ty += prev_bty
        typer.echo(f"\nRefined from previous compensation:")
        typer.echo(f"  prev front: tx={prev_ftx:+.4f}mm  ty={prev_fty:+.4f}mm")
        typer.echo(f"  prev back:  tx={prev_btx:+.4f}mm  ty={prev_bty:+.4f}mm")

    typer.echo(f"\nAccumulated compensation:")
    typer.echo(f"  front: tx={front_tx:+.4f}mm  ty={front_ty:+.4f}mm")
    typer.echo(f"  back:  tx={back_tx:+.4f}mm  ty={back_ty:+.4f}mm")

    RESULT_FILE.write_text(json.dumps({
        "back_shift_x_mm": round(dx, 4),
        "back_shift_y_mm": round(dy, 4),
        "accumulated_front_tx_mm": round(front_tx, 4),
        "accumulated_front_ty_mm": round(front_ty, 4),
        "accumulated_back_tx_mm": round(back_tx, 4),
        "accumulated_back_ty_mm": round(back_ty, 4),
        "front_reproj_err_mm": round(res.front.reproj_error_mm, 4),
        "back_reproj_err_mm": round(res.back.reproj_error_mm, 4),
    }, indent=2) + "\n")
    typer.echo(f"\nResults saved to {RESULT_FILE}")


@app.command()
def verify(
    out: Path = typer.Option(Path("verify.pdf"), "--out", help="Output PDF path."),
    paper: str = typer.Option("letter", "--paper", help=f"Paper size. One of: {', '.join(sorted(PAPERS))}"),
    safe_inset_mm: float = typer.Option(12.0, "--safe-inset-mm", help="Inset from paper edge for the printed border (mm)."),
    marker_size_mm: float = typer.Option(22.0, "--marker-size-mm", help="ArUco marker size (mm)."),
    marker_margin_mm: float = typer.Option(
        15.0,
        "--marker-margin-mm",
        help="Distance from paper edge to marker outer edge (mm).",
    ),
    border_inset_mm: Optional[float] = typer.Option(
        None,
        "--border-inset-mm",
        help="Inset from paper edge for the printed border (mm). Defaults to --safe-inset-mm.",
    ),
) -> None:
    """Generate a verification PDF with per-side compensation from calibration_result.json."""
    if not RESULT_FILE.exists():
        typer.echo(f"Error: {RESULT_FILE} not found. Run 'analyze' first.", err=True)
        raise typer.Exit(1)
    data = json.loads(RESULT_FILE.read_text())
    front_tx = float(data["accumulated_front_tx_mm"])
    front_ty = float(data["accumulated_front_ty_mm"])
    back_tx = float(data["accumulated_back_tx_mm"])
    back_ty = float(data["accumulated_back_ty_mm"])
    typer.echo(f"Using values from {RESULT_FILE}:")
    typer.echo(f"  front: tx={front_tx:+.4f}mm  ty={front_ty:+.4f}mm")
    typer.echo(f"  back:  tx={back_tx:+.4f}mm  ty={back_ty:+.4f}mm")

    pdf = generate_verify_pdf(
        out,
        paper=paper,
        front_tx_mm=front_tx,
        front_ty_mm=front_ty,
        back_tx_mm=back_tx,
        back_ty_mm=back_ty,
        safe_inset_mm=safe_inset_mm,
        marker_size_mm=marker_size_mm,
        marker_margin_mm=marker_margin_mm,
        border_inset_mm=border_inset_mm,
    )
    typer.echo(str(pdf))


def main() -> None:
    app()


if __name__ == "__main__":
    main()
