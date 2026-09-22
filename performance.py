# performance.py
import os
import time
import json
import cv2
import numpy as np

from Shamir_share.Shamir import GenShare as ShamirGen, Recover as ShamirRecover
from CRT_share.CRT       import GenShare as CrtGen,    Recover as CrtRecover


HERE = os.path.dirname(os.path.abspath(__file__))

# ---------------- 全局默认参数 ----------------
Shamir_cases = [
    # (p, n, k)
    (257,  5, 3),
    (257, 10, 5),
]

CRT_cases = [
    # (n, k)  —— chunk_bytes 用 CRT 模块默认 8
    (5, 3),
    (10, 5),
]

addr   = './perf_out/'
REPEAT = 3
IMG_REL = 'shamir_test_rgb.png'


# =====================================================================
# 工具
# =====================================================================
def _time_it(fn, *args, repeat=3, **kwargs):
    times, result = [], None
    for _ in range(repeat):
        t0 = time.perf_counter()
        result = fn(*args, **kwargs)
        times.append(time.perf_counter() - t0)
    return result, min(times), sum(times) / len(times)


def _ensure_dir(ADDR):
    full = os.path.join(HERE, ADDR)
    os.makedirs(full, exist_ok=True)
    return full


def _share_path(name, i, ADDR):
    return os.path.join(HERE, ADDR, f'{name}_share_{i:02d}.npz')


def _fmt_bytes(b):
    for unit in ("B", "KB", "MB", "GB"):
        if b < 1024:
            return f"{b:.2f} {unit}"
        b /= 1024
    return f"{b:.2f} TB"


# =====================================================================
# 单组参数评估 —— Shamir
# =====================================================================
def evaluate_shamir(P, N, K, origin_img, ADDR, repeat=3):
    """origin_img: np.ndarray (H, W, C) uint8"""
    _ensure_dir(ADDR)

    # ---- 1) 分片 ----
    shares, t_gen_min, t_gen_avg = _time_it(
        ShamirGen, p=P, n=N, k=K, img=origin_img, repeat=repeat
    )

    # ---- 2) 恢复 ----
    rec, t_rec_min, t_rec_avg = _time_it(
        ShamirRecover, shares[:K], repeat=repeat
    )

    # ---- 3) 大小 ----
    sizes = []
    for i, s in enumerate(shares, start=1):
        path = _share_path("Shamir", i, ADDR)
        s.save(path)
        sizes.append(os.path.getsize(path))

    # ---- 4) 精度 ----
    diff = np.abs(rec.astype(np.int64) - origin_img.astype(np.int64))
    max_err = int(diff.max())
    exact   = bool(np.array_equal(rec, origin_img))
    ratio   = float(np.mean(rec == origin_img))

    return {
        "algorithm":     "Shamir",
        "p":             int(P),
        "n":             int(N),
        "k":             int(K),
        "chunk_bytes":   None,
        "t_gen_min":     t_gen_min,
        "t_gen_avg":     t_gen_avg,
        "t_rec_min":     t_rec_min,
        "t_rec_avg":     t_rec_avg,
        "single_size":   sizes[0] if sizes else 0,
        "total_size":    sum(sizes),
        "max_err":       max_err,
        "exact":         exact,
        "correct_ratio": ratio,
    }


# =====================================================================
# 单组参数评估 —— CRT
# =====================================================================
def evaluate_crt(N, K, origin_bytes, ADDR, repeat=3, chunk_bytes=8):
    """origin_bytes: bytes —— 直接用文件原始字节"""
    _ensure_dir(ADDR)

    # ---- 1) 分片（无 p / bits 参数）----
    shares, t_gen_min, t_gen_avg = _time_it(
        CrtGen, img=origin_bytes, n=N, k=K,
        chunk_bytes=chunk_bytes, repeat=repeat
    )

    # ---- 2) 恢复（返回 bytes）----
    rec, t_rec_min, t_rec_avg = _time_it(
        CrtRecover, shares[:K], repeat=repeat
    )

    # ---- 3) 大小 ----
    sizes = []
    for i, s in enumerate(shares, start=1):
        path = _share_path("CRT", i, ADDR)
        s.save(path)
        sizes.append(os.path.getsize(path))

    # ---- 4) 精度：字节级对比 ----
    exact = bool(rec == origin_bytes)
    if exact:
        max_err = 0
        ratio = 1.0
    else:
        # 字节不同的位置数
        if len(rec) != len(origin_bytes):
            max_err = abs(len(rec) - len(origin_bytes))
            ratio = 0.0
        else:
            diff_pos = sum(1 for a, b in zip(rec, origin_bytes) if a != b)
            max_err = 1                      # 字节级，没有"误差大小"，只标记不同
            ratio = 1.0 - diff_pos / len(origin_bytes)

    m0_bits = shares[0].meta.extra[0].bit_length()
    m_i_bits = shares[0].meta.moduli[0].bit_length()

    return {
        "algorithm":     "CRT",
        "p":             m0_bits,            # 用 m0 位宽代替 p，方便展示
        "n":             int(N),
        "k":             int(K),
        "chunk_bytes":   int(chunk_bytes),
        "m0_bits":       m0_bits,
        "m_i_bits":      m_i_bits,
        "t_gen_min":     t_gen_min,
        "t_gen_avg":     t_gen_avg,
        "t_rec_min":     t_rec_min,
        "t_rec_avg":     t_rec_avg,
        "single_size":   sizes[0] if sizes else 0,
        "total_size":    sum(sizes),
        "max_err":       max_err,
        "exact":         exact,
        "correct_ratio": ratio,
    }


# =====================================================================
# 打印
# =====================================================================
def print_result(r):
    extra = ""
    if r["algorithm"] == "CRT":
        extra = (f", chunk={r['chunk_bytes']}B, "
                 f"m0={r['m0_bits']}b, m_i={r['m_i_bits']}b")
    print(f"\n=== {r['algorithm']}  (n={r['n']}, k={r['k']}{extra}) ===")
    print(f"  分片耗时    : min {r['t_gen_min']*1000:.2f} ms | "
          f"avg {r['t_gen_avg']*1000:.2f} ms")
    print(f"  恢复耗时    : min {r['t_rec_min']*1000:.2f} ms | "
          f"avg {r['t_rec_avg']*1000:.2f} ms")
    print(f"  单 share    : {_fmt_bytes(r['single_size'])}")
    print(f"  总 share    : {_fmt_bytes(r['total_size'])}  (n={r['n']} 份)")
    print(f"  最大绝对误差: {r['max_err']}")
    print(f"  完全恢复等级: {'✅ 完全恢复' if r['exact'] else '⚠️ 部分恢复'} "
          f"(正确比例 {r['correct_ratio']*100:.4f}%)")


def print_summary_table(results):
    print("\n" + "=" * 120)
    print("汇总")
    print("=" * 120)
    header = (f"{'算法':<8}{'n':>4}{'k':>4}{'chunk':>7}"
              f"{'分片(ms)':>13}{'恢复(ms)':>13}"
              f"{'单share':>12}{'总share':>12}"
              f"{'max_err':>10}{'完全恢复':>10}")
    print(header)
    print("-" * 120)
    for r in results:
        chunk = f"{r['chunk_bytes']}B" if r["chunk_bytes"] else "-"
        print(f"{r['algorithm']:<8}{r['n']:>4}{r['k']:>4}{chunk:>7}"
              f"{r['t_gen_avg']*1000:>13.2f}{r['t_rec_avg']*1000:>13.2f}"
              f"{_fmt_bytes(r['single_size']):>12}{_fmt_bytes(r['total_size']):>12}"
              f"{r['max_err']:>10}{'✅' if r['exact'] else '❌':>10}")
    print("=" * 120)


# =====================================================================
# 扫描
# =====================================================================
def test_shamir_cases(origin_img, ADDR, cases, repeat=3):
    print(f"\n########## Shamir ##########")
    results = []
    for (P, N, K) in cases:
        try:
            r = evaluate_shamir(P, N, K, origin_img, ADDR, repeat)
            results.append(r)
            print_result(r)
        except Exception as e:
            print(f"\n[Shamir p={P}, n={N}, k={K}] 失败: "
                  f"{type(e).__name__}: {e}")
    return results


def test_crt_cases(origin_bytes, ADDR, cases, repeat=3, chunk_bytes=8):
    print(f"\n########## CRT ##########")
    results = []
    for (N, K) in cases:
        try:
            r = evaluate_crt(N, K, origin_bytes, ADDR,
                             repeat=repeat, chunk_bytes=chunk_bytes)
            results.append(r)
            print_result(r)
        except Exception as e:
            print(f"\n[CRT n={N}, k={K}, chunk={chunk_bytes}B] 失败: "
                  f"{type(e).__name__}: {e}")
    return results


# =====================================================================
# 主入口
# =====================================================================
def performance(SHAMIR_CASES, CRT_CASES, ADDR, REPEAT=3,
                img_rel=IMG_REL, chunk_bytes=8, save_json=True):
    """
    - SHAMIR_CASES: [(p, n, k), ...]
    - CRT_CASES:    [(n, k), ...]   —— p / bits 不再需要
    - ADDR:         相对 HERE 的输出目录
    - REPEAT:       每组重复次数
    - img_rel:      相对 HERE 的测试图路径
    - chunk_bytes:  CRT 分组字节数（默认 8）
    """
    img_path = os.path.join(HERE, img_rel)
    if not os.path.exists(img_path):
        raise FileNotFoundError(f"找不到 {img_path}")

    # ---- 加载两种视角 ----
    origin_img = cv2.imread(img_path)
    if origin_img is None:
        raise FileNotFoundError(f"cv2 无法读取 {img_path}")
    with open(img_path, 'rb') as f:
        origin_bytes = f.read()

    print(f"图像: {img_path}")
    print(f"尺寸: {origin_img.shape}, dtype={origin_img.dtype}, "
          f"像素数={origin_img.size}")
    print(f"文件字节: {len(origin_bytes)} 字节")
    print(f"输出目录: {_ensure_dir(ADDR)}")
    print(f"重复次数: {REPEAT}")

    results = []
    results += test_shamir_cases(origin_img, ADDR, SHAMIR_CASES, REPEAT)
    results += test_crt_cases(origin_bytes, ADDR, CRT_CASES, REPEAT,
                              chunk_bytes=chunk_bytes)

    if results:
        print_summary_table(results)

    if save_json:
        out_path = os.path.join(HERE, ADDR, "performance_result.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"\n结果已保存: {out_path}")

    return results


# =====================================================================
if __name__ == "__main__":
    performance(Shamir_cases, CRT_cases, addr, REPEAT)