# printer-keystone

CLI tool to:

1. Generate a duplex calibration PDF (front + back) with fiducial marks.
2. Analyze scans of the printed front/back to compute the back-vs-front alignment offset in millimeters.

## Install

Because some systems enforce PEP 668 ("externally managed environment"), you may need a virtualenv:

```bash
python3 -m venv .venv
.venv/bin/python -m ensurepip --upgrade
.venv/bin/python -m pip install -U pip
.venv/bin/python -m pip install -e .
```

```bash
python3 -m pip install -e .
```

## Workflow

1. Generate the calibration PDF.

```bash
printer-keystone generate --paper letter --out calibration.pdf
```

If your printer can’t print close to the edges, increase the safe inset:

```bash
printer-keystone generate --paper letter --safe-inset-mm 15 --out calibration.pdf
```

2. Print it duplex (100% scale; no "fit to page").

3. Scan the printed sheet (both sides).

You can pass images (`.png/.jpg`) or PDFs (`.pdf`). If your scanner outputs a 2-page PDF, pass it twice and pick pages.

4. Analyze and get offsets:

```bash
printer-keystone analyze \
  --front front.pdf --front-page 1 \
  --back back.pdf --back-page 1 \
  --paper letter \
  --debug-dir debug_out
```

The command prints:

- `back_shift_x_mm` / `back_shift_y_mm`: how much to shift the *back side* to match the front (front-view coordinates).
- Extra diagnostics: estimated rotation and scale per side.

## Notes / Assumptions

- This computes alignment relative to detected page bounds. If the scan does not include physical paper edges, the analyzer may treat the scan image bounds as the page.
- For best results:
  - Scan with auto-crop off if possible.
  - Use a flatbed or a consistent ADF; avoid skew.
  - Ensure the full page edges are visible in the scan.

## Printable Margins (Important)

Many printers cannot print close to the paper edge, which can cause the border/fiducials to be clipped.

If the border does not print, regenerate with a larger inset:

```bash
printer-keystone generate --paper letter --safe-inset-mm 15 --out calibration.pdf
```

## Debug Output And Diagnostics

If the tool reports a crazy `scale` (far from 1.0) or large `rot_deg`, enable debug output:

```bash
printer-keystone analyze ... --debug-dir debug_out
```

Check:
- `debug_out/*_paper_corners.png`: red dots must land on the actual page corners (not on a marker/border).
- `debug_out/*_markers.png`: should show detected IDs `10,11,12,13,14`.

What “good” typically looks like:
- `scale` is close to `1.0`
- `rot_deg` is close to `0`
- `markers` includes all five IDs `[10, 11, 12, 13, 14]` on both sides

If you see `scale` around `10+` or `rot_deg` around `5+`, the analyzer probably used the wrong contour as the “page” (often a marker or the inset border). Re-scan with full page edges visible and good contrast around the paper, or increase `--safe-inset-mm` so the border prints.
