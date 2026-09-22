下面是按「顶部语言切换 + 中文完整在前 + 英文完整在后」重构的 `README.md`。

---

# Tessera

**基于 Shamir 与 CRT 的阈值图像秘密共享 · Threshold Image Secret Sharing via Shamir and CRT**

[中文](#中文) · [English](#english)

---
---

<a id="中文"></a>

# 中文

Tessera 将一张 RGB 图像拆分为 *n* 份份额，任意 *k* 份即可无损重建原图——并经过逐像素与逐字节的双重校验。项目内置两套独立后端与一套基准测试。

## 项目结构

```text
.
├── CRT_share/
│   ├── CRT.py             # CRT 共享算法
│   └── test_CRT.py        # CRT 后端测试
├── Shamir_share/
│   ├── Shamir.py          # GF(p) 上的 Shamir 秘密共享
│   └── test_Shamir.py     # Shamir 后端测试
├── Share.py               # Share 数据类（自适应存储、序列化）
├── main.py                # 入口——运行完整流程
├── performance.py         # 基准测试（耗时、体积、误差）
├── report.py              # 报告数据模型 + Markdown 生成器
├── environment.txt        # pip / uv 依赖清单
├── environment.yml        # conda 环境定义
├── shamir_test_rgb.png    # 两个后端共用的测试图片
└── README.md
```

## 环境配置

任选一种包管理器：

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

依赖：`numpy`、`pillow`、`opencv-python`。

## 使用方式

运行完整流程：

```bash
python main.py
```

`main.py` 依次完成：

1. 读取 `shamir_test_rgb.png` 作为源图。
2. 分别为 **Shamir** 与 **CRT** 后端生成份额。
3. 使用不同的份额子集恢复图像。
4. 对恢复结果做像素级校验与文件级 SHA-256 校验。
5. 调用 `performance.py` 运行性能基准。
6. 将最终报告写入 `report.md`。

## 生成结果

运行 `main.py` 后会生成 Markdown 报告：

```text
report.md
```

报告包含：

- 各后端的分片与恢复耗时。
- 单份份额体积与总份额体积。
- 重建误差（`max_err`）与完全恢复状态。
- 像素级与哈希级校验结果。

基准测试输出示例：

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

## 后端对比

| | Shamir | CRT |
|---|---|---|
| 域 / 模数 | 素数 `p`（默认 257） | 每份模数 `m₁…mₙ` |
| 运算粒度 | 单个像素值 | 8 字节块 |
| 单份份额（256×256×3，n=5，k=3） | ~250 KB | ~5.8 KB |
| 总份额 | ~1.22 MB | ~29 KB |
| 分片耗时 | ~155 ms | ~8 ms |
| 恢复耗时 | ~17.5 ms | ~2.6 ms |
| 重建误差 | 0 | 0 |
| 压缩特性 | 高熵，几乎不可压 | 保留结构，压缩率高 |

**Shamir** 提供最强的理论保证，是密码学意义上的标准选择。  
**CRT** 对图像数据更紧凑，因为其余数保留了原始像素的低熵结构。

两者统一暴露在 `GenShare` / `Recover` API 下。

## API 示例

```python
import numpy as np
from PIL import Image
from Shamir_share.Shamir import GenShare, Recover
from Share import Share

img = np.array(Image.open("shamir_test_rgb.png").convert("RGB"))

# 拆成 5 份，任意 3 份可重建
shares = GenShare(p=257, n=5, k=3, img=img)
for i, s in enumerate(shares, 1):
    s.save(f"share_{i:02d}.npz")

# 用第 1、3、5 份恢复
recovered = Recover([Share.load(f"share_{i:02d}.npz") for i in (1, 3, 5)])
assert np.array_equal(img, recovered)
```

## 存储模型

`Share` 类按数据范围自动选择最小的存储类型：

| 数据范围 | 存储类型 |
|---|---|
| `0 ≤ v ≤ 2⁸-1` | `uint8` |
| `0 ≤ v ≤ 2¹⁶-1` | `uint16` |
| `0 ≤ v ≤ 2³²-1` | `uint32` |
| `0 ≤ v ≤ 2⁶⁴-1` | `uint64` |
| 更大 / 有符号极值 | 64 位 limb 拆分或 `object` 兜底 |

份额通过 `np.savez_compressed` 序列化。纯整数数据无需 pickle。

## 校验

每次测试都会报告：

- 与源图的**像素级一致性**。
- 写回 PNG 的 **SHA-256** 与源文件比对。
- **PIL 与 OpenCV** 两条写回路径各自独立验证。
- **份额不足检测**——少于 *k* 份时抛出 `ValueError`。

输出示例：

```text
test00: 使用 shares [1, 2, 3] 恢复
  恢复结果 vs 原图（像素级）:              ✅ 完全一致
  PIL 写回文件 SHA-256 vs origin:          ✅ 一致
  cv2 写回文件 SHA-256 vs origin:          ❌ 不同（编码器差异，非数据错误）
```

> **说明：** 只有当写回所用的编码器与生成源 PNG 的编码器一致时，文件级 hash 才会相同。跨编码器比较时，应以像素级一致性或内存数组 hash 作为正确性判据。

## 设计说明

- **Shamir 份额是高熵的。** 每份份额在 `[0, p)` 上均匀分布，压缩收益很小。份额大小与像素值数量成正比，而与图像冗余度无关。
- **CRT 份额保留结构。** 因为 CRT 以字节块为运算单位，且余数常常等于原始整数，所以份额流保留了像素相关性，压缩率高。
- **自适应存储。** `Values` 会检查数据范围并选择最窄的定长 dtype，仅在必要时回退到位打包或 64 位 limb。
- **单一当前格式。** 序列化器只读写一种格式，不保留旧版本兼容路径。

## 许可证

MIT — 详见 `LICENSE`。

[回到顶部 ↑](#tessera)

---
---

<a id="english"></a>

# English

Tessera splits an RGB image into *n* shares such that any *k* of them losslessly reconstruct the original — verified pixel-by-pixel and byte-for-byte. It ships with two independent backends and a built-in benchmark.

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

## Backends at a Glance

| | Shamir | CRT |
|---|---|---|
| Field / modulus | Prime `p` (default 257) | Per-share moduli `m₁…mₙ` |
| Unit of operation | One pixel value | 8-byte chunk |
| Share size (256×256×3, n=5, k=3) | ~250 KB | ~5.8 KB |
| Total shares | ~1.22 MB | ~29 KB |
| Split time | ~155 ms | ~8 ms |
| Recover time | ~17.5 ms | ~2.6 ms |
| Reconstruction error | 0 | 0 |
| Compression | High-entropy, hard to compress | Retains structure, compresses well |

**Shamir** gives the strongest theoretical guarantees and is the standard cryptographic choice.  
**CRT** is far more compact for image data because its residues preserve the low-entropy structure of the original pixels.

Both are exposed behind a unified `GenShare` / `Recover` API.

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

## Storage Model

The `Share` class stores values in the smallest sufficient representation:

| Data range | Storage |
|---|---|
| `0 ≤ v ≤ 2⁸-1` | `uint8` |
| `0 ≤ v ≤ 2¹⁶-1` | `uint16` |
| `0 ≤ v ≤ 2³²-1` | `uint32` |
| `0 ≤ v ≤ 2⁶⁴-1` | `uint64` |
| Larger / signed extremes | 64-bit limbs or `object` fallback |

Shares are serialized with `np.savez_compressed`. Integer-only data requires no pickle.

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

## Design Notes

- **Shamir shares are high-entropy.** Each share is uniformly distributed over `[0, p)`, so compression yields little. Share size scales with the number of pixel values, not with image redundancy.
- **CRT shares retain structure.** Because CRT operates on byte chunks and residues often equal the original integer, the share stream preserves pixel correlation and compresses well.
- **Adaptive storage.** `Values` inspects the data range and selects the narrowest fixed-width dtype, falling back to bit-packing or 64-bit limbs only when needed.
- **Single, current format.** The serializer reads and writes one format; no legacy compatibility paths.

## License

MIT — see `LICENSE` for details.

[Back to top ↑](#tessera)
