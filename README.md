# printer-keystone

CLI tool for duplex printer alignment calibration. Measures and corrects the front-to-back offset your printer introduces during duplex printing.

## Install

```bash
# Using uv (recommended)
uv sync

# Or with pip
python3 -m venv .venv
.venv/bin/pip install -e .
```

## Quick Start

```bash
./generate.sh        # Generate calibration PDF
                     # Print duplex (100% scale, long-edge flip)
                     # Scan both sides as front.png / back.png
./analyze.sh         # Measure offset → saves calibration_result.json
./verify.sh          # Generate verification PDF with compensation
                     # Print duplex, hold to light to check alignment
```

## Full Workflow

### 1. Generate calibration sheet

```bash
printer-keystone generate --paper letter --out calibration.pdf
```

Prints a 2-page PDF with ArUco fiducial markers (IDs 10–14) and a registration target. No border is drawn — the analysis uses paper edge detection.

### 2. Print and scan

- Print duplex at **100% scale** (no fit-to-page), **long-edge flip**.
- Scan both sides on a flatbed scanner. Keep full paper edges visible (disable auto-crop).
- Save as `front.png` and `back.png`.

### 3. Analyze

```bash
printer-keystone analyze --front front.png --back back.png --paper letter --debug-dir debug
```

Outputs:
- `back_shift_x_mm` / `back_shift_y_mm`: total front-to-back misalignment.
- Per-side diagnostics: translation, rotation, scale, reprojection error.
- Saves per-side compensation values to `calibration_result.json`.

### 4. Generate verification print

```bash
printer-keystone verify --paper letter
```

Reads `calibration_result.json` and generates `verify.pdf` with per-side marker offsets to compensate for the printer's error. Both the front and back pages are individually corrected.

Print duplex and hold to light — the registration bullseye targets should overlap.

### 5. Iterative refinement

If the verification print still shows visible offset, scan it and refine:

```bash
printer-keystone analyze \
  --front verifyfront.png --back verifyback.png \
  --paper letter --debug-dir debug --refine
```

The `--refine` flag adds the measured residual to the existing accumulated compensation. Then run `verify` again. Each iteration converges closer to perfect alignment.

Repeat until the measured offset is within your target (e.g., <0.25mm).

## Shell Scripts

| Script | Purpose |
|--------|---------|
| `generate.sh` | Generate calibration PDF (letter paper) |
| `analyze.sh` | Analyze front.png/back.png scans (pass `--front`/`--back` to override) |
| `verify.sh` | Generate verification PDF from calibration_result.json |

All scripts accept extra flags via `"$@"`, e.g.:
```bash
./analyze.sh --front verifyfront.png --back verifyback.png --refine
```

## Tips for Accuracy

- **No border detection**: Analysis uses paper edge detection, not the printed border. This gives better results (scale ~1.002, reproj_err <0.1mm).
- **Scanner DPI**: Higher DPI improves sub-pixel marker detection. 600+ DPI recommended for <0.25mm accuracy.
- **Consistent scanner placement**: Always place the sheet flush against the same corner.
- **Iterative refinement**: One round of `--refine` typically halves the remaining error.

## Debug Output

```bash
printer-keystone analyze ... --debug-dir debug
```

Check:
- `debug/*_paper_corners.png`: red dots on detected page corners.
- `debug/*_markers.png`: detected marker IDs and centers.

Healthy diagnostics:
- `scale` close to `1.0` (within 0.5%)
- `rot_deg` close to `0` (within 0.2°)
- `reproj_err` < 0.2mm
- All 5 markers `[10, 11, 12, 13, 14]` detected
