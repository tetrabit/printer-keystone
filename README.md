# printer-keystone

CLI tool to:

1. Generate a duplex calibration PDF (front + back) with fiducial marks.
2. Analyze scans of the printed front/back to compute the back-vs-front alignment offset in millimeters.

## Install

```bash
python3 -m pip install -e .
```

## Workflow

1. Generate the calibration PDF.

```bash
printer-keystone generate --paper letter --out calibration.pdf
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

- This computes alignment relative to detected paper edges (not relative to the printed fiducials themselves).
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

The analyzer primarily uses the paper edges; if your scanner crops the page or the tool reports a crazy `scale`
(far from 1.0), re-scan with the full page edges visible or enable debug output:

```bash
printer-keystone analyze ... --debug-dir debug_out
```

Check:
- `debug_out/*_paper_corners.png`: red dots must land on the actual page corners (not on a marker/border).
- `debug_out/*_markers.png`: should show detected IDs `10,11,12,13,14`.
