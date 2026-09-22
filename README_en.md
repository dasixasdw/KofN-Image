# KofN-Image

**Threshold image secret sharing via Shamir and CRT.**

KofN-Image splits an RGB image into *n* shares such that any *k* of them losslessly reconstruct the original — verified pixel-by-pixel and byte-for-byte. It ships with two independent backends and a built-in benchmark.

---

## Project Structure

```text
.
├── CRT_share/
│   ├── CRT.py             # CRT-based sharing algorithm
│   └── test_CRT.py        # Tests for the CRT backend
├── Shamir_share/
│   ├── Shamir.py          # Shamir's Secret Sharing over GF(p)
│   └── test_Shamir.py     # Tests for the Shamir backend
├── Share.py               # Share data class (adaptive storage, serialization)
├── main.py                # Entry point — runs the full pipeline
├── performance.py         # Benchmark harness (timing, size, error)
├── report.py              # Report data model + Markdown generator
├── environment.txt        # pip / uv dependency list
├── environment.yml        # conda environment definition
├── shamir_test_rgb.png    # Test image used by both backends
└── README.md
```

---

## Environment Setup

Pick whichever package manager you prefer:

**uv**

```bash
uv add -r environment.txt
```

**pip**

```bash
pip install -r environment.txt
```

**conda**

```bash
conda env create -f environment.yml
```

Requirements: `numpy`, `pillow`, `opencv-python`.

---

## Usage

Run the full pipeline:

```bash
python main.py
```

`main.py` performs the following:

1. Loads `shamir_test_rgb.png` as the source image.
2. Generates shares for both the **Shamir** and **CRT** backends.
3. Recovers the image from various share subsets.
4. Verifies reconstruction at pixel level and via file-level SHA-256.
5. Runs the performance benchmark in `performance.py`.
6. Emits the final report to `report.md`.

---

## Output

Running `main.py` writes a Markdown report to:

```text
report.md
```

The report contains:

- Per-backend split and recovery timings.
- Share sizes (single share and total).
- Reconstruction error (`max_err`) and full-recovery status.
- Pixel-level and hash-level verification results.

Example benchmark table:

```text
========================================================================================================================
算法         n   k  chunk       分片(ms)       恢复(ms)      单share      总share   max_err      完全恢复
------------------------------------------------------------------------------------------------------------------------
Shamir     5   3      -       154.55        17.52   250.69 KB     1.22 MB         0         ✅
Shamir    10   5      -       336.00        29.74   250.63 KB     2.45 MB         0         ✅
CRT        5   3     8B         7.82         2.58     5.83 KB    29.14 KB         0         ✅
CRT       10   5     8B        14.42         3.71     5.93 KB    59.27 KB         0         ✅
========================================================================================================================
```

---

## Backends at a Glance

|                                  | Shamir                         | CRT                                |
| -------------------------------- | ------------------------------ | ---------------------------------- |
| Field / modulus                  | Prime `p` (default 257)        | Per-share moduli `m₁…mₙ`           |
| Unit of operation                | One pixel value                | 8-byte chunk                       |
| Share size (256×256×3, n=5, k=3) | ~250 KB                        | ~5.8 KB                            |
| Total shares                     | ~1.22 MB                       | ~29 KB                             |
| Split time                       | ~155 ms                        | ~8 ms                              |
| Recover time                     | ~17.5 ms                       | ~2.6 ms                            |
| Reconstruction error             | 0                              | 0                                  |
| Compression behavior             | High-entropy, hard to compress | Retains structure, compresses well |

**Shamir** gives the strongest theoretical guarantees and is the standard cryptographic choice.  
**CRT** is far more compact for image data because its residues preserve the low-entropy structure of the original pixels.

Both are exposed behind a unified `GenShare` / `Recover` API.

---

## API Sketch

```python
import numpy as np
from PIL import Image
from Shamir_share.Shamir import GenShare, Recover
from Share import Share

img = np.array(Image.open("shamir_test_rgb.png").convert("RGB"))

# Split into 5 shares, any 3 reconstruct
shares = GenShare(p=257, n=5, k=3, img=img)
for i, s in enumerate(shares, 1):
    s.save(f"share_{i:02d}.npz")

# Recover from shares 1, 3, 5
recovered = Recover([Share.load(f"share_{i:02d}.npz") for i in (1, 3, 5)])
assert np.array_equal(img, recovered)
```

---

## Storage Model

The `Share` class stores values in the smallest sufficient representation:

| Data range               | Storage                           |
| ------------------------ | --------------------------------- |
| `0 ≤ v ≤ 2⁸-1`           | `uint8`                           |
| `0 ≤ v ≤ 2¹⁶-1`          | `uint16`                          |
| `0 ≤ v ≤ 2³²-1`          | `uint32`                          |
| `0 ≤ v ≤ 2⁶⁴-1`          | `uint64`                          |
| Larger / signed extremes | 64-bit limbs or `object` fallback |

Shares are serialized with `np.savez_compressed`. Integer-only data requires no pickle.

---

## Verification

Every test reports:

- **Pixel-level equality** against the source image.
- **SHA-256 of the written-back PNG** compared to the source file.
- **Both PIL and OpenCV** write-back paths, validated independently.
- **Insufficient-share detection** — recovery with fewer than *k* shares raises `ValueError`.

Example output:

```text
test00: recovering from shares [1, 2, 3]
  Recovered vs. original (pixel-level):     ✅ identical
  PIL  write-back file SHA-256 vs origin:   ✅ match
  cv2  write-back file SHA-256 vs origin:   ❌ differs (encoder difference, not data error)
```

> **Note:** File-level hash matches only when the writing encoder matches the one that produced the source PNG. Pixel-level and in-memory array hashes are the authoritative correctness checks across encoders.

---

## Design Notes

- **Shamir shares are high-entropy.** Each share is uniformly distributed over `[0, p)`, so compression yields little. Share size scales with the number of pixel values, not with image redundancy.
- **CRT shares retain structure.** Because CRT operates on byte chunks and residues often equal the original integer, the share stream preserves pixel correlation and compresses well.
- **Adaptive storage.** `Values` inspects the data range and selects the narrowest fixed-width dtype, falling back to bit-packing or 64-bit limbs only when needed.
- **Single, current format.** The serializer reads and writes one format; no legacy compatibility paths.

---

## License

MIT — see `LICENSE` for details.
