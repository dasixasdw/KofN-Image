# test_Shamir.py
from Shamir_share.Shamir import GenShare, Recover
import os
import hashlib
import numpy as np
import cv2
from Share import Share
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))

p    = 257
n    = 5
k    = 3
test = [[1, 2, 3], [1, 4, 5]]
addr = './given_test/'

PNG_COMPRESS = 6
ORIGIN_PATH  = os.path.join(HERE, '..', 'shamir_test_rgb.png')


# ---------------- 基础工具 ----------------

def _ensure_dir(ADDR):
    full = os.path.join(HERE, ADDR)
    os.makedirs(full, exist_ok=True)
    return full


def _share_path(i, ADDR):
    return os.path.join(HERE, ADDR, f'Shamir_share_{i:02d}.npz')


def file_hash(path):
    """直接对磁盘上的图片文件做 SHA-256。"""
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def pixel_equal(a, b):
    a, b = np.asarray(a), np.asarray(b)
    if a.shape != b.shape:
        return False, f"shape 不同 {a.shape} vs {b.shape}"
    if a.dtype != b.dtype:
        return False, f"dtype 不同 {a.dtype} vs {b.dtype}"
    if not np.array_equal(a, b):
        diff = np.abs(a.astype(np.int64) - b.astype(np.int64))
        return False, (f"{int(np.count_nonzero(diff))} 个像素不同, "
                       f"max|Δ|={int(diff.max())}")
    return True, "完全一致"


# ---------------- 恢复与写回 ----------------

def load_shares(ids, ADDR):
    return [Share.load(_share_path(i, ADDR)) for i in ids]


def _pil_writeback(recovered, out_path):
    Image.fromarray(recovered).save(
        out_path, format='PNG', compress_level=PNG_COMPRESS, optimize=False
    )


def _cv2_writeback(recovered, out_path):
    cv2.imwrite(
        out_path,
        cv2.cvtColor(recovered, cv2.COLOR_RGB2BGR),
        [cv2.IMWRITE_PNG_COMPRESSION, PNG_COMPRESS],
    )


def recover_and_check(origin_img, tag_ids, name, ADDR, h_origin, summary):
    print(f"\n{name}: 使用 shares {tag_ids} 恢复")
    shares = load_shares(tag_ids, ADDR)
    tag = ''.join(map(str, tag_ids))

    recovered = Recover(shares)
    if recovered.dtype != origin_img.dtype:
        recovered = recovered.astype(origin_img.dtype)

    ok = True

    # ========== 1) 恢复结果 vs 原图：只做像素级 ==========
    print("  -- 恢复结果 vs 原图（仅像素级）--")
    px_ok, px_msg = pixel_equal(origin_img, recovered)
    print(f"    像素级: {'✅' if px_ok else '❌'} {px_msg}")
    ok = ok and px_ok
    summary['recover'].append((name, px_ok))

    # ========== 2) PIL 写回实验 ==========
    print("  -- PIL 写回实验（文件字节 hash）--")
    out_pil = os.path.join(HERE, ADDR, f'Recovered_Shamir_{tag}_pil.png')
    _pil_writeback(recovered, out_pil)
    h_pil = file_hash(out_pil)
    size_pil = os.path.getsize(out_pil)
    same_pil = (h_pil == h_origin)
    print(f"    文件: {out_pil}  ({size_pil/1024:.2f} KB)")
    print(f"    origin: {h_origin}")
    print(f"    PIL   : {h_pil}")
    print(f"    文件字节 hash: {'✅ 一致' if same_pil else '❌ 不同'}")
    ok = ok and same_pil
    summary['pil'].append((name, same_pil, size_pil, h_pil))

    # ========== 3) cv2 写回实验 ==========
    print("  -- cv2 写回实验（文件字节 hash）--")
    out_cv2 = os.path.join(HERE, ADDR, f'Recovered_Shamir_{tag}_cv2.png')
    _cv2_writeback(recovered, out_cv2)
    h_cv2 = file_hash(out_cv2)
    size_cv2 = os.path.getsize(out_cv2)
    same_cv2 = (h_cv2 == h_origin)
    print(f"    文件: {out_cv2}  ({size_cv2/1024:.2f} KB)")
    print(f"    origin: {h_origin}")
    print(f"    cv2   : {h_cv2}")
    print(f"    文件字节 hash: {'✅ 一致' if same_cv2 else '❌ 不同'}")
    ok = ok and same_cv2
    summary['cv2'].append((name, same_cv2, size_cv2, h_cv2))

    print(f"  => {name} 总体: {'✅ 通过' if ok else '❌ 失败'}")
    return ok


# ---------------- 主流程 ----------------

def setup_shares(P, N, K, origin_img, ADDR):
    _ensure_dir(ADDR)
    paths = [_share_path(i, ADDR) for i in range(1, N + 1)]
    if all(os.path.exists(path) for path in paths):
        print(f"已存在 Shamir shares ({ADDR})，跳过生成")
        return
    print(f"生成 Shamir shares: p={P}, n={N}, k={K}, addr={ADDR}")
    shares = GenShare(p=P, n=N, k=K, img=origin_img)
    for i, s in enumerate(shares, start=1):
        path = _share_path(i, ADDR)
        s.save(path)
        print(f"  已保存: {path}  (x={s.x})")


def _print_summary(summary, h_origin):
    print("\n" + "=" * 70)
    print("汇总")
    print("=" * 70)

    # --- 恢复 ---
    print("\n[恢复结果 vs 原图 · 像素级]")
    print(f"  {'用例':<10} {'结果':<6}")
    for name, px_ok in summary['recover']:
        print(f"  {name:<10} {'✅' if px_ok else '❌':<6}")
    rec_pass = sum(1 for _, v in summary['recover'] if v)
    print(f"  小计: {rec_pass}/{len(summary['recover'])} 通过")

    # --- PIL ---
    print("\n[PIL 写回 · 文件字节 hash vs origin]")
    print(f"  {'用例':<10} {'hash一致':<8} {'大小(KB)':<10} {'hash(前16)':<20}")
    for name, same, size, h in summary['pil']:
        print(f"  {name:<10} {'✅' if same else '❌':<8} "
              f"{size/1024:<10.2f} {h[:16]:<20}")
    pil_pass = sum(1 for _, v, _, _ in summary['pil'] if v)
    print(f"  小计: {pil_pass}/{len(summary['pil'])} 通过")

    # --- cv2 ---
    print("\n[cv2 写回 · 文件字节 hash vs origin]")
    print(f"  {'用例':<10} {'hash一致':<8} {'大小(KB)':<10} {'hash(前16)':<20}")
    for name, same, size, h in summary['cv2']:
        print(f"  {name:<10} {'✅' if same else '❌':<8} "
              f"{size/1024:<10.2f} {h[:16]:<20}")
    cv2_pass = sum(1 for _, v, _, _ in summary['cv2'] if v)
    print(f"  小计: {cv2_pass}/{len(summary['cv2'])} 通过")

    # --- 对比结论 ---
    print("\n[结论对比]")
    print(f"  origin 文件字节 hash = {h_origin}")
    print(f"  恢复结果像素级      : {rec_pass}/{len(summary['recover'])} ✅")
    print(f"  PIL  文件字节 hash   : {pil_pass}/{len(summary['pil'])} "
          f"{'✅' if pil_pass == len(summary['pil']) else '❌'}")
    print(f"  cv2  文件字节 hash   : {cv2_pass}/{len(summary['cv2'])} "
          f"{'✅' if cv2_pass == len(summary['cv2']) else '❌'}")
    if pil_pass > cv2_pass:
        print("  → PIL 与 origin 编码器同源，文件字节可复现；"
              "cv2 与 origin 编码器不同，字节必然不同（非数据错误）")
    print("=" * 70)


def test_shamir(P, N, K, TEST, ADDR):
    origin_img = np.array(Image.open(ORIGIN_PATH).convert('RGB'))
    h_origin   = file_hash(ORIGIN_PATH)
    print(f"原图: {ORIGIN_PATH}")
    print(f"      shape={origin_img.shape}, dtype={origin_img.dtype}, "
          f"像素数={origin_img.size}")
    print(f"      origin 文件字节 hash = {h_origin}")

    setup_shares(P, N, K, origin_img, ADDR)

    summary = {'recover': [], 'pil': [], 'cv2': []}

    all_ok = True
    for idx, tag_ids in enumerate(TEST):
        all_ok &= recover_and_check(
            origin_img, tag_ids, f'test{idx:02d}', ADDR, h_origin, summary
        )

    print(f"\ntest_insufficient: 只用 {K-1} 份（应抛异常）")
    ids = [i + 1 for i in range(K - 1)]
    try:
        Recover(load_shares(ids, ADDR))
        print("  ❌ 没有抛异常，逻辑有问题！")
        all_ok = False
    except ValueError as e:
        print(f"  ✅ 正确抛出: {e}")

    _print_summary(summary, h_origin)
    return all_ok


if __name__ == "__main__":
    test_shamir(p, n, k, test, addr)