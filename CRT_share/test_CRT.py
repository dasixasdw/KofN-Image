# test_CRT.py
from CRT_share.CRT import GenShare, Recover
import os
import hashlib
from Share import Share

HERE = os.path.dirname(os.path.abspath(__file__))

N    = 5
K    = 3
TEST = [[1, 2, 3], [1, 4, 5]]
ADDR = './given_test/'


def _ensure_dir(ADDR):
    full = os.path.join(HERE, ADDR)
    os.makedirs(full, exist_ok=True)
    return full


def _share_path(i, ADDR):
    return os.path.join(HERE, ADDR, f'CRT_share_{i:02d}.npz')


def load_shares(ids, ADDR):
    return [Share.load(_share_path(i, ADDR)) for i in ids]


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# =====================================================================
def recover_and_check(origin_bytes, tag_ids, name, ADDR):
    """用 shares 恢复出完整文件字节，和原始文件字节对比。"""
    print(f"\n{name}: 使用 shares {tag_ids} 恢复")
    shares = load_shares(tag_ids, ADDR)
    data = Recover(shares)

    same = (data == origin_bytes)
    print(f"  字节级一致: {same}  ({len(data)} / {len(origin_bytes)} 字节)")

    tag = ''.join(map(str, tag_ids))
    out = os.path.join(HERE, ADDR, f'Recovered_CRT_{tag}.png')
    with open(out, 'wb') as f:
        f.write(data)
    print(f"  已保存: {out}")
    print(f"  SHA-256 原文件: {_sha256(origin_bytes)}")
    print(f"  SHA-256 恢复后: {_sha256(data)}")
    return same


def setup_shares(N, K, origin_bytes, ADDR):
    _ensure_dir(ADDR)
    paths = [_share_path(i, ADDR) for i in range(1, N + 1)]
    if all(os.path.exists(path) for path in paths):
        print(f"已存在 CRT shares ({ADDR})，跳过生成")
        return

    print(f"生成 CRT shares: n={N}, k={K}")
    shares = GenShare(img=origin_bytes, n=N, k=K)
    for i, s in enumerate(shares, start=1):
        path = _share_path(i, ADDR)
        s.save(path)
        m0 = s.meta.extra[0]
        print(f"  已保存: {path}  (x={s.x}, "
              f"m0={m0.bit_length()}b, "
              f"m_i={s.meta.moduli[0].bit_length()}b, "
              f"N_blocks={s.values.size})")


def test_crt(N, K, TEST, ADDR):
    src_path = os.path.join(HERE, '..', 'shamir_test_rgb.png')
    if not os.path.exists(src_path):
        raise FileNotFoundError(f"找不到 {src_path}")
    with open(src_path, 'rb') as f:
        origin_bytes = f.read()
    print(f"文件: {src_path}")
    print(f"大小: {len(origin_bytes)} 字节")
    print(f"SHA-256: {_sha256(origin_bytes)}")

    setup_shares(N, K, origin_bytes, ADDR)

    for idx, tag_ids in enumerate(TEST):
        recover_and_check(origin_bytes, tag_ids, f'test{idx:02d}', ADDR)

    print(f"\ntest_insufficient: 只用 {K-1} 份（应抛异常）")
    ids = [i + 1 for i in range(K - 1)]
    try:
        Recover(load_shares(ids, ADDR))
        print("  ❌ 没有抛异常，逻辑有问题！")
    except ValueError as e:
        print(f"  ✅ 正确抛出: {e}")


if __name__ == "__main__":
    test_crt(N, K, TEST, ADDR)